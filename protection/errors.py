"""Failures are explicit and must never be converted to normal zero scores."""


class InvalidScenarioError(ValueError):
    """Invalid generated or stored research input."""


class InvalidProtectionError(ValueError):
    """Invalid submitted edge identifiers or budget violation."""


class EvaluationError(RuntimeError):
    """Incomplete evaluation; diagnostics are not an official score."""

    def __init__(self, message, *, reason='evaluation_failed', diagnostics=None):
        super().__init__(message)
        self.reason = reason
        self.diagnostics = diagnostics


class DeadlineExceeded(TimeoutError):
    """The caller's monotonic deadline has expired."""
