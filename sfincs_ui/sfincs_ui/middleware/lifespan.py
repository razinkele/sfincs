"""Run coroutines at ASGI lifespan startup and shutdown.

The job runner needs a running event loop, which exists only once uvicorn is
up; starting it from the first request would race. Startup runs the hook
before the inner app's startup; shutdown runs it after the inner app's
shutdown. A startup hook failure is logged, never fatal: the banner already
reports a broken environment, and a reconciliation error must not stop the
pages from serving.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class LifespanMiddleware:
    def __init__(self, app, on_startup=None, on_shutdown=None):
        self.app = app
        self._on_startup = on_startup
        self._on_shutdown = on_shutdown

    async def __call__(self, scope, receive, send):
        if scope["type"] != "lifespan":
            await self.app(scope, receive, send)
            return

        async def wrapped_receive():
            message = await receive()
            if message["type"] == "lifespan.startup" and self._on_startup is not None:
                try:
                    await self._on_startup()
                except Exception:
                    logger.exception("startup hook failed; continuing without it")
            return message

        async def wrapped_send(message):
            await send(message)
            if message["type"] == "lifespan.shutdown.complete" and self._on_shutdown is not None:
                try:
                    await self._on_shutdown()
                except Exception:
                    logger.exception("shutdown hook failed")

        await self.app(scope, wrapped_receive, wrapped_send)
