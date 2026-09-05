"""Viewport / client detection. Does not change ranking or targets."""

from __future__ import annotations

_MOBILE_TOKENS = (
    "iphone",
    "ipod",
    "ipad",
    "android",
    "webos",
    "blackberry",
    "iemobile",
    "opera mini",
)


def user_agent_is_mobile(ua: str) -> bool:
    """True for phone/tablet browsers. Desktop Chrome/Safari/Edge stay false."""
    text = str(ua or "").lower()
    if not text:
        return False
    if any(token in text for token in _MOBILE_TOKENS):
        return True
    return "mobile" in text


def is_mobile_browser() -> bool:
    """Read the current Streamlit request UA. Fail-closed (desktop) if unknown."""
    try:
        import streamlit as st

        headers = getattr(getattr(st, "context", None), "headers", None)
        if headers is None:
            return False
        ua = headers.get("User-Agent") or headers.get("user-agent") or ""
    except Exception:
        return False
    return user_agent_is_mobile(str(ua))
