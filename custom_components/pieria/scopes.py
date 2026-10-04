"""Token scope helper."""

from __future__ import annotations

from .api import Info

REQUIRED_SCOPES = ("read", "control")


def missing_scope(info: Info) -> bool:
    """True when the server reports token scopes and read or control is absent.

    Servers that do not report scopes are given the benefit of the doubt.
    """
    scopes = info.get("token_scopes")
    if scopes is None:
        return False
    return any(scope not in scopes for scope in REQUIRED_SCOPES)
