from __future__ import annotations

from src.data_refresh.external_market import is_valid_korea_10y_nominal


def test_korea_10y_rejects_negative_and_real_rate_like_values() -> None:
    assert not is_valid_korea_10y_nominal(-1.99)
    assert not is_valid_korea_10y_nominal(-2.3)
    assert not is_valid_korea_10y_nominal(0.0)


def test_korea_10y_accepts_nominal_range() -> None:
    assert is_valid_korea_10y_nominal(4.12)
    assert is_valid_korea_10y_nominal(3.5)
    assert is_valid_korea_10y_nominal(0.8)
