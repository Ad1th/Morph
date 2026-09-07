"""User-space TCP proxy: cross-platform network latency and packet-loss simulation.

Zero-dependency, zero-privilege alternative to native network shaping (tc/netem,
dnctl+pfctl, Clumsy). The target application connects to `listen_port` on
localhost instead of the real upstream host; the proxy relays bytes to the real
upstream through a per-direction *delay line*.

    Target App --> localhost:PROXY_PORT --> [delay line] --> upstream host:port

Semantics (these are what make the emulation TCP-realistic):

* ``latency_ms`` is the ROUND-TRIP time, matching what ``ping`` reports and what
  a captured profile stores. Each direction adds ``latency_ms / 2`` of one-way
  delay. Chunks are *pipelined*: every chunk is scheduled for delivery at
  ``arrival + one_way`` without blocking the reader, so throughput is bounded by
  the link, never by ``chunk_count x latency``.
* ``packet_loss_percent`` never corrupts or drops bytes. TCP does not lose data
  on a lossy path -- it retransmits. A "lost" chunk is therefore delivered
  LATE, after a simulated retransmission stall: the first retransmission
  timeout is ``max(200 ms, 3 x RTT)`` and doubles on every consecutive loss
  of the same chunk (RTO exponential backoff). Ordering is preserved, so a
  stalled chunk head-of-line blocks the chunks behind it, exactly as a real
  TCP receive window does. After ``max_retransmits`` consecutive losses the
  path is declared dead and the connection is reset (``ECONNRESET`` in the
  target), which is how a 100 % loss / "offline" profile surfaces.
* ``bandwidth_kbps`` is an optional token bucket per direction, shared by all
  connections through the proxy (one link), independent of latency.
* ``seed`` (or the ``MORPH_SEED`` environment variable) makes the loss pattern
  reproducible from run to run.
"""

from __future__ import annotations

import asyncio
import os
import random
from typing import Self

_CHUNK_SIZE = 4096
# Retransmission schedule. RFC 6298 puts the minimum RTO at 1 s; Linux uses
# 200 ms, which is what a developer watching a stalled request actually sees.
_MIN_RTO_S = 0.200
_RTO_RTT_MULTIPLIER = 3.0
_MAX_RTO_S = 60.0
# Consecutive losses of one chunk before the path is declared dead. Six is far
# below Linux's tcp_retries2 (15, ~15 min) on purpose: a test harness must
# surface "offline" as a reset within seconds, not minutes.
_DEFAULT_MAX_RETRANSMITS = 6
# Bytes queued in one direction before the reader pauses (backpressure), so a
# fast sender behind a long delay cannot buffer without bound.
_HIGH_WATER_BYTES = 8 * 1024 * 1024


class _PathDead(Exception):
    """Raised inside a relay when retransmissions are exhausted."""


_DEAD = b"<morph:path-dead>"  # queue sentinel; compared by identity, never written


def _seed_from_env() -> int | None:
    raw = os.environ.get("MORPH_SEED")
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError:
        return None


class _Link:
    """Per-direction shared state: the bandwidth token bucket."""

    __slots__ = ("bytes_per_s", "next_free_at")

    def __init__(self, bytes_per_s: float | None) -> None:
        self.bytes_per_s = bytes_per_s
        self.next_free_at = 0.0

    def transmit_done_at(self, now: float, nbytes: int) -> float:
        """When the last byte of a chunk leaves the wire, honouring the bucket."""
        if not self.bytes_per_s:
            return now
        start = max(now, self.next_free_at)
        self.next_free_at = start + nbytes / self.bytes_per_s
        return self.next_free_at


class ProxyServer:
    def __init__(
        self,
        upstream_host: str,
        upstream_port: int,
        listen_host: str = "127.0.0.1",
        listen_port: int = 0,
        latency_ms: float = 0.0,
        packet_loss_percent: float = 0.0,
        bandwidth_kbps: float | None = None,
        jitter_ms: float = 0.0,
        seed: int | None = None,
        max_retransmits: int = _DEFAULT_MAX_RETRANSMITS,
        chunk_size: int = _CHUNK_SIZE,
    ):
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.latency_ms = float(latency_ms or 0.0)
        self.packet_loss_percent = float(packet_loss_percent or 0.0)
        self.bandwidth_kbps = bandwidth_kbps
        self.jitter_ms = float(jitter_ms or 0.0)
        self.max_retransmits = max_retransmits
        self.chunk_size = chunk_size

        self.seed = seed if seed is not None else _seed_from_env()
        self.rng = random.Random(self.seed)

        bytes_per_s = (bandwidth_kbps * 1000.0 / 8.0) if bandwidth_kbps else None
        self._links = {"up": _Link(bytes_per_s), "down": _Link(bytes_per_s)}

        self._server: asyncio.base_events.Server | None = None
        self._connections: set[asyncio.Task] = set()
        # Observability for tests and the fidelity report.
        self.stats = {"chunks": 0, "losses": 0, "resets": 0, "stall_s": 0.0}

    # ----------------------------------------------------------- properties

    @property
    def one_way_s(self) -> float:
        return self.latency_ms / 2000.0

    @property
    def rtt_s(self) -> float:
        return self.latency_ms / 1000.0

    @property
    def base_rto_s(self) -> float:
        return max(_MIN_RTO_S, _RTO_RTT_MULTIPLIER * self.rtt_s)

    @property
    def port(self) -> int:
        """Actual bound listen port (resolved after start() when listen_port=0)."""
        if self._server is None:
            raise RuntimeError("proxy is not started")
        return self._server.sockets[0].getsockname()[1]

    # ------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, self.listen_host, self.listen_port
        )

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        # A relay parked on a retransmission stall or on a peer that never
        # sends EOF would keep wait_closed() from returning; cancel them and
        # wait for their cleanup so no task outlives the proxy.
        tasks = list(self._connections)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._connections.clear()
        await self._server.wait_closed()
        self._server = None

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.stop()

    # --------------------------------------------------------------- relay

    async def _handle_client(
        self, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._connections.add(task)

        upstream_writer: asyncio.StreamWriter | None = None
        try:
            try:
                upstream_reader, upstream_writer = await asyncio.open_connection(
                    self.upstream_host, self.upstream_port
                )
            except OSError:
                return

            pumps = [
                asyncio.ensure_future(
                    self._pump(client_reader, upstream_writer, self._links["up"])
                ),
                asyncio.ensure_future(
                    self._pump(upstream_reader, client_writer, self._links["down"])
                ),
            ]
            try:
                done, pending = await asyncio.wait(pumps, return_when=asyncio.FIRST_EXCEPTION)
                reset = any(
                    (not t.cancelled()) and isinstance(t.exception(), _PathDead) for t in done
                )
                failed = any((not t.cancelled()) and t.exception() is not None for t in done)
                if failed:
                    for t in pending:
                        t.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)
                elif pending:
                    # One direction reached EOF cleanly; the other may still
                    # be delivering (keep-alive response after request EOF).
                    await asyncio.gather(*pending, return_exceptions=True)
                if reset:
                    self.stats["resets"] += 1
                    for w in (client_writer, upstream_writer):
                        _abort(w)
            finally:
                for t in pumps:
                    if not t.done():
                        t.cancel()
                await asyncio.gather(*pumps, return_exceptions=True)
        finally:
            if task is not None:
                self._connections.discard(task)
            for w in (client_writer, upstream_writer):
                _close(w)

    def _stall_for_chunk(self) -> tuple[float, bool]:
        """(retransmission delay for one chunk, path_dead).

        Each transmission attempt is lost with probability p. A loss costs one
        RTO, and the RTO doubles for the next attempt of the same chunk. When
        `max_retransmits` consecutive attempts are lost the path is dead: the
        connection is reset once that accumulated stall has elapsed, never
        instantly -- a dead path looks like silence first, then ECONNRESET.
        """
        p = self.packet_loss_percent
        if p <= 0.0:
            return 0.0, False
        stall = 0.0
        rto = self.base_rto_s
        attempts = 0
        while self.rng.random() * 100.0 < p:
            attempts += 1
            self.stats["losses"] += 1
            stall += rto
            rto = min(rto * 2.0, _MAX_RTO_S)
            if attempts >= self.max_retransmits:
                return stall, True
        return stall, False

    async def _pump(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, link: _Link
    ) -> None:
        """Relay reader -> writer through an ordered delay line.

        The reader never sleeps: each chunk is stamped with a delivery time and
        handed to a writer task that drains the queue in order.
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[float, bytes | None]] = asyncio.Queue()
        buffered = 0
        drained = asyncio.Event()
        drained.set()

        async def deliver() -> None:
            nonlocal buffered
            while True:
                due, chunk = await queue.get()
                delay = due - loop.time()
                if delay > 0:
                    await asyncio.sleep(delay)
                if chunk is _DEAD:
                    raise _PathDead()
                if chunk is None:
                    if writer.can_write_eof():
                        try:
                            writer.write_eof()
                        except (OSError, RuntimeError):
                            pass
                    return
                writer.write(chunk)
                buffered -= len(chunk)
                if buffered < _HIGH_WATER_BYTES:
                    drained.set()
                await writer.drain()

        deliver_task = asyncio.ensure_future(deliver())
        last_due = 0.0
        try:
            while True:
                if buffered >= _HIGH_WATER_BYTES:
                    drained.clear()
                    await drained.wait()
                chunk = await reader.read(self.chunk_size)
                now = loop.time()
                if not chunk:
                    # Forward the half-close, in order, behind any queued data.
                    # Without it a response of unknown length hangs until the
                    # client's read timeout.
                    queue.put_nowait((max(now + self.one_way_s, last_due), None))
                    break
                self.stats["chunks"] += 1
                stall, dead = self._stall_for_chunk()
                self.stats["stall_s"] += stall
                sent_at = link.transmit_done_at(now, len(chunk))
                jitter = abs(self.rng.gauss(0.0, self.jitter_ms / 1000.0)) if self.jitter_ms else 0.0
                due = max(sent_at + self.one_way_s + jitter + stall, last_due)
                last_due = due
                if dead:
                    # Stop reading; the reset fires when the stall has elapsed.
                    queue.put_nowait((due, _DEAD))
                    break
                buffered += len(chunk)
                queue.put_nowait((due, chunk))
            await deliver_task
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass
        finally:
            if not deliver_task.done():
                deliver_task.cancel()
                await asyncio.gather(deliver_task, return_exceptions=True)


def _abort(writer: asyncio.StreamWriter | None) -> None:
    if writer is None:
        return
    try:
        writer.transport.abort()
    except Exception:
        pass


def _close(writer: asyncio.StreamWriter | None) -> None:
    if writer is None:
        return
    try:
        writer.close()
    except Exception:
        pass


async def _self_check() -> None:
    """Runnable check: RTT is observable, bytes survive loss, 100 % loss blocks."""

    async def echo_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            writer.close()

    echo_server = await asyncio.start_server(echo_handler, "127.0.0.1", 0)
    echo_port = echo_server.sockets[0].getsockname()[1]
    loop = asyncio.get_running_loop()

    # Latency: a ping through the proxy should take about one RTT (50 ms), not 2x.
    async with ProxyServer("127.0.0.1", echo_port, latency_ms=50) as proxy:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
        start = loop.time()
        writer.write(b"ping")
        await writer.drain()
        response = await reader.readexactly(4)
        elapsed = loop.time() - start
        writer.close()
        assert response == b"ping", "echo payload should survive the proxy unmodified"
        assert 0.045 <= elapsed < 0.4, f"expected ~50ms RTT, got {elapsed * 1000:.1f}ms"

    # Throughput: latency must not cap bandwidth. 1 MB at 50 ms RTT, well under 1 s.
    payload = os.urandom(1024 * 1024)
    async with ProxyServer("127.0.0.1", echo_port, latency_ms=50) as proxy:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
        start = loop.time()
        writer.write(payload)
        await writer.drain()
        got = await reader.readexactly(len(payload))
        elapsed = loop.time() - start
        writer.close()
        assert got == payload, "bytes were corrupted in transit"
        assert elapsed < 1.0, f"1 MB took {elapsed:.2f}s: latency is acting as a bandwidth cap"

    # Loss: nothing is ever lost or reordered, it is just late.
    async with ProxyServer("127.0.0.1", echo_port, packet_loss_percent=30, seed=7) as proxy:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
        blob = bytes(range(256)) * 512  # 128 KB, ordered pattern
        writer.write(blob)
        await writer.drain()
        got = await asyncio.wait_for(reader.readexactly(len(blob)), timeout=30)
        writer.close()
        assert got == blob, "loss must be a delay, never corruption"
        assert proxy.stats["losses"] > 0, "30% loss produced no retransmissions"

    # 100 % loss: nothing arrives (the path is dead, the target sees a stall then a reset).
    async with ProxyServer("127.0.0.1", echo_port, packet_loss_percent=100) as proxy:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
        writer.write(b"ping")
        await writer.drain()
        try:
            await asyncio.wait_for(reader.read(4096), timeout=0.3)
            raise AssertionError("100% packet loss should have stalled the chunk")
        except TimeoutError:
            pass
        writer.close()

    echo_server.close()
    await echo_server.wait_closed()
    print("proxy self-check: OK")


if __name__ == "__main__":
    asyncio.run(_self_check())
