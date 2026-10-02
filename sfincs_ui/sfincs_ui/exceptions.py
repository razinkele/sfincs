"""Typed errors raised by services; pages turn them into notifications (spec section 5)."""


class SfincsUiError(Exception):
    """Base class: the message is safe to show to the user."""


class NotAllowed(SfincsUiError):
    pass


class NotFound(SfincsUiError):
    pass


class QueueFull(SfincsUiError):
    pass


class QuotaExceeded(SfincsUiError):
    pass


class LaunchRefused(SfincsUiError):
    pass


class TemplateError(SfincsUiError):
    pass


class BuildError(SfincsUiError):
    pass
