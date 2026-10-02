from unittest.mock import AsyncMock

from sfincs_ui.middleware.lifespan import LifespanMiddleware


async def _lifespan_messages():
    msgs = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]

    async def receive():
        return msgs.pop(0)

    return receive


async def test_hooks_run_around_the_inner_app():
    order = []

    async def inner(scope, receive, send):
        while True:
            m = await receive()
            order.append(m["type"])
            if m["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            else:
                await send({"type": "lifespan.shutdown.complete"})
                return

    async def up():
        order.append("up")

    async def down():
        order.append("down")

    mw = LifespanMiddleware(inner, on_startup=up, on_shutdown=down)
    await mw({"type": "lifespan"}, await _lifespan_messages(), AsyncMock())
    assert order == ["up", "lifespan.startup", "lifespan.shutdown", "down"]


async def test_startup_failure_is_logged_not_fatal(caplog):
    async def inner(scope, receive, send):
        m = await receive(); await send({"type": "lifespan.startup.complete"})
        m = await receive(); await send({"type": "lifespan.shutdown.complete"})

    async def boom():
        raise RuntimeError("reconcile exploded")

    mw = LifespanMiddleware(inner, on_startup=boom, on_shutdown=None)
    await mw({"type": "lifespan"}, await _lifespan_messages(), AsyncMock())
    assert "reconcile exploded" in caplog.text


async def test_http_passes_through():
    inner = AsyncMock()
    await LifespanMiddleware(inner, None, None)({"type": "http"}, AsyncMock(), AsyncMock())
    inner.assert_called_once()
