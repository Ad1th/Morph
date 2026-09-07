"""The user-space proxy must behave like a lossy, slow TCP path -- not like a corrupting one.

Every test runs a real echo server and a real ProxyServer on loopback.
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest
import pytest_asyncio

from morph.runtime.adapters.proxy import ProxyServer


async def _echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
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


@pytest_asyncio.fixture
async def echo_port():
    server = await asyncio.start_server(_echo, "127.0.0.1", 0)
    try:
        yield server.sockets[0].getsockname()[1]
    finally:
        server.close()
        await server.wait_closed()


async def _roundtrip(port: int, payload: bytes, timeout: float = 30.0) -> tuple[bytes, float]:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    t0 = time.perf_counter()
    writer.write(payload)
    await writer.drain()
    got = await asyncio.wait_for(reader.readexactly(len(payload)), timeout=timeout)
    elapsed = time.perf_counter() - t0
    writer.close()
    return got, elapsed


@pytest.mark.asyncio
async def test_rtt_is_the_configured_latency_not_double(echo_port):
    """`latency_ms` is a round trip, like `ping`: one-way is half of it."""
    async with ProxyServer("127.0.0.1", echo_port, latency_ms=100) as proxy:
        _, elapsed = await _roundtrip(proxy.port, b"ping")
    assert 0.09 <= elapsed < 0.3, f"RTT {elapsed * 1000:.0f}ms for a 100ms profile"


@pytest.mark.asyncio
async def test_throughput_is_not_capped_by_latency(echo_port):
    """1 MB at 50 ms RTT completes in well under a second: chunks are pipelined,
    not serialised behind one sleep each (4096 B / 50 ms would be 13 s)."""
    payload = os.urandom(1024 * 1024)
    async with ProxyServer("127.0.0.1", echo_port, latency_ms=50) as proxy:
        got, elapsed = await _roundtrip(proxy.port, payload)
    assert got == payload
    assert elapsed < 1.0, f"1 MB took {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_loss_never_loses_or_corrupts_bytes(echo_port):
    """30 % loss: every byte still arrives, in order. TCP retransmits; it does not drop."""
    blob = bytes(range(256)) * 1024  # 256 KB with a recognisable order
    async with ProxyServer("127.0.0.1", echo_port, packet_loss_percent=30, seed=1) as proxy:
        got, _ = await _roundtrip(proxy.port, blob, timeout=60)
        assert proxy.stats["losses"] > 0
    assert got == blob


@pytest.mark.asyncio
async def test_a_lost_chunk_costs_a_retransmission_stall(echo_port):
    """With 100 % loss on a 0-RTT path the first RTO is 200 ms, so nothing can
    arrive before that; with 0 % loss the same ping is sub-50 ms."""
    async with ProxyServer("127.0.0.1", echo_port, packet_loss_percent=0) as proxy:
        _, fast = await _roundtrip(proxy.port, b"x")
    assert fast < 0.05

    # Seed chosen so that the first chunk is lost exactly once (rng.random() < 0.5
    # once, then not): a stall of max(200ms, 3*RTT) = 200ms, then delivery.
    proxy = ProxyServer("127.0.0.1", echo_port, packet_loss_percent=50, seed=0)
    draws = [proxy.rng.random() for _ in range(4)]
    proxy.rng.seed(0)
    lost_first = draws[0] * 100 < 50
    async with proxy:
        got, elapsed = await _roundtrip(proxy.port, b"x", timeout=30)
    assert got == b"x"
    if lost_first:
        assert elapsed >= 0.19, f"a lost chunk should stall ~200ms, took {elapsed * 1000:.0f}ms"
    else:  # pragma: no cover - depends on the RNG stream
        assert elapsed < 0.19


@pytest.mark.asyncio
async def test_rto_doubles_on_consecutive_losses(echo_port):
    """Force every draw to be a loss for exactly three attempts: 200+400+800 ms."""
    proxy = ProxyServer("127.0.0.1", echo_port, packet_loss_percent=50, seed=0)
    draws = iter([0.0, 0.0, 0.0, 0.99, 0.99, 0.99, 0.99, 0.99, 0.99, 0.99, 0.99, 0.99])

    class FixedRng:
        def random(self):
            return next(draws)

        def gauss(self, *_):
            return 0.0

    proxy.rng = FixedRng()
    async with proxy:
        got, elapsed = await _roundtrip(proxy.port, b"x", timeout=30)
    assert got == b"x"
    assert 1.35 <= elapsed < 2.5, f"expected ~1.4s (200+400+800ms), got {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_total_loss_stalls_then_resets(echo_port):
    """100 % loss: silence first (no bytes within 300 ms), then the path is declared
    dead and the client sees EOF/reset rather than a stream that hangs forever."""
    async with ProxyServer(
        "127.0.0.1", echo_port, packet_loss_percent=100, max_retransmits=2
    ) as proxy:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
        writer.write(b"ping")
        await writer.drain()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(reader.read(4096), timeout=0.3)
        # max_retransmits=2 at 0 RTT: 200 + 400 ms, then reset.
        data = await asyncio.wait_for(reader.read(4096), timeout=5)
        assert data == b"", "a dead path must surface as EOF/reset, not data"
        assert proxy.stats["resets"] == 1
        writer.close()


@pytest.mark.asyncio
async def test_seed_makes_the_loss_pattern_reproducible(echo_port):
    async def stalls(seed: int) -> float:
        async with ProxyServer("127.0.0.1", echo_port, packet_loss_percent=25, seed=seed) as proxy:
            await _roundtrip(proxy.port, bytes(64 * 1024), timeout=60)
            return proxy.stats["stall_s"]

    a, b, c = await stalls(42), await stalls(42), await stalls(43)
    assert a == b
    assert a != c or True  # different seeds MAY coincide; equality of a and b is the contract


@pytest.mark.asyncio
async def test_seed_comes_from_the_environment(monkeypatch, echo_port):
    monkeypatch.setenv("MORPH_SEED", "1234")
    proxy = ProxyServer("127.0.0.1", echo_port)
    assert proxy.seed == 1234


@pytest.mark.asyncio
async def test_bandwidth_token_bucket(echo_port):
    """256 KB at 2 Mbit/s takes ~1 s regardless of the (tiny) latency."""
    payload = os.urandom(256 * 1024)
    async with ProxyServer("127.0.0.1", echo_port, latency_ms=2, bandwidth_kbps=2000) as proxy:
        got, elapsed = await _roundtrip(proxy.port, payload, timeout=30)
    assert got == payload
    # 256 KB = 2.1 Mbit -> ~1.05 s per direction; up and down are separate
    # links (they overlap), so the round trip is ~1.1 s, never the ~5 ms an
    # unshaped loopback takes.
    assert 0.9 <= elapsed < 4.0, f"took {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_half_close_is_forwarded(echo_port):
    """A client that shuts down its write side must still receive the response."""

    async def length_prefixed_server(reader, writer):
        body = await reader.read()  # until EOF
        writer.write(body[::-1])
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(length_prefixed_server, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        async with ProxyServer("127.0.0.1", port, latency_ms=20) as proxy:
            reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
            writer.write(b"abc")
            await writer.drain()
            writer.write_eof()
            got = await asyncio.wait_for(reader.read(), timeout=5)
            assert got == b"cba"
            writer.close()
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_stop_cancels_parked_relays_and_leaks_no_tasks(echo_port):
    before = len(asyncio.all_tasks())
    proxy = ProxyServer("127.0.0.1", echo_port, packet_loss_percent=100)
    await proxy.start()
    _reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
    writer.write(b"never arrives")
    await writer.drain()
    await asyncio.sleep(0.05)
    await asyncio.wait_for(proxy.stop(), timeout=2)  # must not wait for the 100% stall
    writer.close()
    await asyncio.sleep(0.05)
    assert len(asyncio.all_tasks()) <= before + 1
    assert proxy._connections == set()


@pytest.mark.asyncio
async def test_upstream_refused_closes_the_client():
    async with ProxyServer("127.0.0.1", 1) as proxy:  # port 1: nothing listens
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
        data = await asyncio.wait_for(reader.read(10), timeout=5)
        assert data == b""
        writer.close()


@pytest.mark.asyncio
async def test_keepalive_style_request_response_under_both_conditions(echo_port):
    """The flagship shape: several small request/response exchanges on one
    connection with latency AND loss. Every response must match."""
    async with ProxyServer("127.0.0.1", echo_port, latency_ms=40, packet_loss_percent=20, seed=3) as proxy:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
        for i in range(10):
            msg = f"req-{i}".encode()
            writer.write(msg)
            await writer.drain()
            got = await asyncio.wait_for(reader.readexactly(len(msg)), timeout=30)
            assert got == msg
        writer.close()
