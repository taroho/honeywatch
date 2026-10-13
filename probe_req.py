"""_handle_login を実際に叩けるか・structlog capture できるか検証する一時スクリプト."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import structlog
from aiohttp.streams import StreamReader
from aiohttp.test_utils import make_mocked_request
from multidict import CIMultiDict

from honeywatch.collector.handler import EventQueue
from honeywatch.honeypot.http import HTTPHoneypot


def make_honeypot() -> HTTPHoneypot:
    hp = HTTPHoneypot(MagicMock(spec=EventQueue))
    hp.emit_event = AsyncMock()  # type: ignore[method-assign]
    return hp


def make_request(method: str, body: bytes | None, remote: str = "203.0.113.5",
                 source_port: int = 44444) -> object:
    headers = CIMultiDict({"User-Agent": "pytest"})
    payload = None
    if body is not None:
        headers["Content-Length"] = str(len(body))
        loop = asyncio.get_event_loop()
        protocol = MagicMock()
        payload = StreamReader(protocol, limit=2**16, loop=loop)
        payload.feed_data(body)
        payload.feed_eof()
    transport = MagicMock()
    transport.get_extra_info.return_value = (remote, source_port)
    req = make_mocked_request(
        method, "/login", headers=headers, payload=payload,
        remote=remote, transport=transport,
    )
    return req


async def main() -> None:
    hp = make_honeypot()

    # GET
    resp = await hp._handle_login(make_request("GET", None))
    print("GET status", resp.status, "server", resp.headers.get("Server"))

    # POST
    hp2 = make_honeypot()
    body = b"email=a%40b.com&password=secret123"
    with structlog.testing.capture_logs() as logs:
        resp = await hp2._handle_login(make_request("POST", body))
    print("POST status", resp.status)
    print("emit calls", hp2.emit_event.await_count)
    ev = hp2.emit_event.await_args.args[0]
    print("event_type", ev.event_type, "protocol", ev.protocol)
    print("source_ip", ev.source_ip, "source_port", ev.source_port, "dest", ev.destination_port)
    print("raw email", ev.raw_data["email"], "raw pw", ev.raw_data["password"])
    print("logs count", len(logs))
    print("secret in logs?", any("secret123" in repr(x) for x in logs))

    # 405
    hp3 = make_honeypot()
    resp = await hp3._handle_login(make_request("PUT", None))
    print("PUT status", resp.status, "emit", hp3.emit_event.await_count)

    # 413 exactly 1MB+1
    hp4 = make_honeypot()
    big = b"a" * (1_048_576 + 1)
    resp = await hp4._handle_login(make_request("POST", b"email=" + big))
    print("BIG status", resp.status, "emit", hp4.emit_event.await_count)


asyncio.run(main())
