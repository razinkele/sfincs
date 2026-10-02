"""Server-side identity resolution for one reactive evaluation.

Pure and dependency-light so the authorization check can be unit-tested
against a real database without a Shiny session.
"""

from __future__ import annotations


def resolve_identity(ws_token: str | None, session_token: str | None, auth_service) -> dict | None:
    """Server-validated identity for one reactive evaluation: the ws token first, then the cookie session. Always consults the database, so logout, deactivation, demotion and deletion take effect on the next call.

    Args:
        ws_token: The raw token from the ``_wsauth`` Shiny input (falsy means none).
        session_token: The raw ``sfincs_ui_session`` cookie seen when the websocket connected.
        auth_service: Anything with ``validate_ws_token`` and ``validate_session``.

    Returns:
        The user dict, or None when neither token validates.
    """
    if ws_token:
        user = auth_service.validate_ws_token(ws_token)
        if user is not None:
            return user
    if session_token:
        return auth_service.validate_session(session_token)
    return None
