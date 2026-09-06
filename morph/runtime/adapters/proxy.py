"""User-space TCP proxy: cross-platform network latency and packet-loss simulation.

Zero-dependency, zero-privilege alternative to native network shaping (tc/netem,
dnctl+pfctl, Clumsy). The target application connects to `listen_port` on
localhost instead of the real upstream host; the proxy relays bytes to the real
upstream while injecting delay and probabilistically dropping chunks.

    Target App --> localhost:PROXY_PORT --> [delay, drop] --> upstream host:port
"""

import asyncio
import random
from typing import Self


class ProxyServer:
    def __init__(
        self,
        upstream_host: str,
        upstream_port: int,
        listen_host: str = "127.0.0.1",
        listen_port: int = 0,
        latency_ms: float = 0.0,
        packet_loss_percent: float = 0.0,
    ):
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.latency_ms = latency_ms
        self.packet_loss_percent = packet_loss_percent
        self._server: asyncio.base_events.Server | None = None

    @property
    def port(self) -> int:
        """Actual bound listen port (resolved after start() when listen_port=0)."""
        if self._server is None:
            raise RuntimeError("proxy is not started")
        return self._server.sockets[0].getsockname()[1]

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, self.listen_host, self.listen_port
        )

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.stop()

    async def _handle_client(
        self, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter
    ) -> None:
        try:
            upstream_reader, upstream_writer = await asyncio.open_connection(
                self.upstream_host, self.upstream_port
            )
        except OSError:
            client_writer.close()
            return

        await asyncio.gather(
            self._pump(client_reader, upstream_writer),
            self._pump(upstream_reader, client_writer),
            return_exceptions=True,
        )

        for writer in (client_writer, upstream_writer):
            writer.close()

    async def _pump(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Relay chunks from reader to writer, injecting latency and packet loss."""
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                if self.latency_ms:
                    await asyncio.sleep(self.latency_ms / 1000)
                if self.packet_loss_percent and random.random() * 100 < self.packet_loss_percent:
                    continue  # simulate a dropped packet: never forward this chunk
                writer.write(chunk)
                await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass


async def _self_check() -> None:
    """Runnable check: latency is observable, and 100% loss actually blocks delivery."""

    async def echo_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        data = await reader.read(4096)
        writer.write(data)
        await writer.drain()
        writer.close()

    echo_server = await asyncio.start_server(echo_handler, "127.0.0.1", 0)
    echo_port = echo_server.sockets[0].getsockname()[1]

    # Latency injection: round trip through the proxy should take at least
    # 2x the configured one-way latency (once per relay direction).
    async with ProxyServer("127.0.0.1", echo_port, latency_ms=50) as proxy:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
        loop = asyncio.get_event_loop()
        start = loop.time()
        writer.write(b"ping")
        await writer.drain()
        response = await reader.read(4096)
        elapsed = loop.time() - start
        writer.close()
        assert response == b"ping", "echo payload should survive the proxy unmodified"
        assert elapsed >= 0.09, f"expected >=~2x50ms latency, got {elapsed * 1000:.1f}ms"

    # Packet loss: 100% loss must prevent delivery entirely.
    async with ProxyServer("127.0.0.1", echo_port, packet_loss_percent=100) as proxy:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
        writer.write(b"ping")
        await writer.drain()
        try:
            await asyncio.wait_for(reader.read(4096), timeout=0.3)
            raise AssertionError("100% packet loss should have dropped the chunk")
        except TimeoutError:
            pass  # expected: nothing arrives
        writer.close()

    echo_server.close()
    await echo_server.wait_closed()
    print("proxy self-check: OK")


if __name__ == "__main__":
    asyncio.run(_self_check())
