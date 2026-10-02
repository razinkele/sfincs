"""uvicorn target: ``uvicorn sfincs_ui.asgi:app``."""

from sfincs_ui.app import create_app

app = create_app()
