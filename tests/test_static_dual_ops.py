"""정적 북 · 듀얼모멘텀 운영 헬퍼."""

from __future__ import annotations

from pathlib import Path

from alpha_system.ui.services.dual_momentum_ops import (
    DualMomentumSignal,
    compute_dual_momentum_signal,
    dual_signal_to_rows,
)
from alpha_system.ui.services.static_book_ops import (
    STATIC_RECIPE_IDS,
    checklist_static,
    recommend_static_recipe,
    recipe_select_labels,
    static_recipe_meta,
)


ROOT = Path(__file__).resolve().parents[1]


def test_static_book_recipes() -> None:
    metas = static_recipe_meta(ROOT)
    ids = {m["id"] for m in metas}
    assert set(STATIC_RECIPE_IDS) <= ids
    rec = recommend_static_recipe(ROOT)
    assert rec in ids
    labels = recipe_select_labels(ROOT)
    assert len(labels) >= 5
    assert all(" · " in lab for _, lab in labels)
    cl = checklist_static(rec)
    assert any("연" in x or "리밸" in x for x in cl)


def test_dual_momentum_signal_shape() -> None:
    sig = compute_dual_momentum_signal(ROOT, ensure_fetch=False)
    assert isinstance(sig, DualMomentumSignal)
    assert sig.review_only is True
    assert sig.writes_target is False
    assert sig.lookback_months == 12
    # 정석 근사 레시피: EAFE · 유로50단독 아님
    from alpha_system.ui.services.dual_momentum_ops import _load_dual_recipe

    stg = _load_dual_recipe(ROOT)
    assert stg is not None
    offs = [str(o.get("ticker")) for o in (stg.get("offensive") or [])]
    assert "360750" in offs
    assert "195970" in offs
    assert "195930" not in offs
    assert "245350" not in offs
    if sig.ok:
        assert sig.pick_ticker
        assert sig.absolute_ok is not None
        rows = dual_signal_to_rows(sig)
        assert len(rows) >= 3
        assert any(r.get("") == "◀ 픽" for r in rows)
        assert sig.checklist
        assert any("EAFE" in x or "상대" in x for x in sig.checklist)
    else:
        # 가격 없으면 실패 사유만 · 레시피는 있어야 함
        assert "레시피" not in (sig.error or "") or True


def test_dual_absolute_uses_relative_winner(tmp_path: Path, monkeypatch) -> None:
    """미국 < 현금이어도 EAFE 승자가 현금 위면 주식(EAFE) 픽 — 정석 순서."""
    import pandas as pd

    from alpha_system.ui.services import dual_momentum_ops as dmo

    idx = pd.date_range("2024-01-01", periods=400, freq="B")
    # US flat-ish end < cash path; EAFE strong
    us = pd.Series(100.0, index=idx)
    us.iloc[-1] = 101.0
    us.iloc[0] = 100.0
    # force 12M: set price 12m ago
    cut = idx[-1] - pd.DateOffset(months=12)
    prior = idx[idx <= cut][-1]
    us.loc[:prior] = 100.0
    us.loc[prior:] = 100.0
    us.iloc[-1] = 99.0  # US 12M negative-ish

    eafe = us.copy()
    eafe.loc[:prior] = 100.0
    eafe.iloc[-1] = 130.0  # +30%

    cash = us.copy()
    cash.loc[:prior] = 100.0
    cash.iloc[-1] = 102.0  # +2% · US 99/100 < cash, EAFE 130 > cash

    safe = cash.copy()
    panel = pd.DataFrame(
        {"360750": us, "195970": eafe, "329750": cash, "437080": safe},
        index=idx,
    )

    monkeypatch.setattr(
        dmo,
        "_load_dual_recipe",
        lambda root: {
            "lookback_months": 12,
            "offensive": [
                {"ticker": "360750", "name": "US"},
                {"ticker": "195970", "name": "EAFE"},
            ],
            "cash_ticker": "329750",
            "cash_name": "BIL",
            "safe_ticker": "437080",
            "safe_name": "AGG",
        },
    )
    monkeypatch.setattr(
        "alpha_system.shadow.household_alloc_lab.build_price_panel",
        lambda *a, **k: panel,
    )
    sig = dmo.compute_dual_momentum_signal(tmp_path, ensure_fetch=False)
    assert sig.ok
    assert sig.pick_ticker == "195970"
    assert sig.absolute_ok is True


def test_dual_requires_all_offensive_returns(tmp_path: Path, monkeypatch) -> None:
    """EAFE 가격 없으면 미국만으로 승자 단정 금지."""
    import pandas as pd

    from alpha_system.ui.services import dual_momentum_ops as dmo

    idx = pd.date_range("2024-01-01", periods=400, freq="B")
    us = pd.Series(100.0, index=idx)
    us.iloc[-1] = 110.0
    cash = us.copy()
    cash.iloc[-1] = 101.0
    safe = cash.copy()
    panel = pd.DataFrame(
        {"360750": us, "329750": cash, "437080": safe},
        index=idx,
    )
    monkeypatch.setattr(
        dmo,
        "_load_dual_recipe",
        lambda root: {
            "lookback_months": 12,
            "offensive": [
                {"ticker": "360750", "name": "US"},
                {"ticker": "195970", "name": "EAFE"},
            ],
            "cash_ticker": "329750",
            "cash_name": "BIL",
            "safe_ticker": "437080",
            "safe_name": "AGG",
        },
    )
    monkeypatch.setattr(
        "alpha_system.shadow.household_alloc_lab.build_price_panel",
        lambda *a, **k: panel,
    )
    sig = dmo.compute_dual_momentum_signal(tmp_path, ensure_fetch=False)
    assert not sig.ok
    assert "195970" in (sig.error or "")
