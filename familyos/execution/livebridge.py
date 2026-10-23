"""The live view's wire: the member's browser to the sitting's browser,
through this server, frame for frame and key for key.

A page served over https may not open a plain ws:// socket, and a phone
cannot reach the browser's socket at all; the console can always reach
this server. So the console opens a websocket here, with a one-time ticket
issued for the sitting, and this relays it to the browser's own debugging
socket. Nothing is read, kept or logged on the way through: a frame is a
string in, the same string out.
"""
from __future__ import annotations

import asyncio
import logging

import websockets

logger = logging.getLogger(__name__)

MAX_MESSAGE = 32 * 1024 * 1024


async def bridge(client, upstream_url: str, *, origin: str) -> None:
    """Relay until either side closes. `client` is a Starlette WebSocket
    already accepted; `upstream_url` is the browser's socket."""
    async with websockets.connect(upstream_url, additional_headers={"Origin": origin}, max_size=MAX_MESSAGE,
                                  open_timeout=15) as upstream:
        async def down() -> None:
            async for message in upstream:
                await client.send_text(message if isinstance(message, str) else message.decode("utf-8", "replace"))

        async def up() -> None:
            while True:
                await upstream.send(await client.receive_text())

        tasks = [asyncio.create_task(down()), asyncio.create_task(up())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in tasks:
                t.cancel()
