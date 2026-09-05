"""Mobile UA detection for compact layout."""

from __future__ import annotations

from alpha_system.ui.services.device import user_agent_is_mobile


def test_phone_and_tablet_are_mobile() -> None:
    assert user_agent_is_mobile(
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
    )
    assert user_agent_is_mobile(
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Mobile Safari/537.36"
    )
    assert user_agent_is_mobile(
        "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
    )


def test_desktop_browsers_are_not_mobile() -> None:
    assert not user_agent_is_mobile(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
    assert not user_agent_is_mobile(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    )
    assert not user_agent_is_mobile("")
