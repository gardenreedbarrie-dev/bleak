"""Errors raised for an invalid map spec."""


class SpecError(ValueError):
    """The map spec is invalid; the message names the offending key."""
