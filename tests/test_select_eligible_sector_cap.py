"""select_eligible — sector_group concentration cap + shortfall."""

from __future__ import annotations

from alpha_system.loader import load_config
from alpha_system.schema import TrancheId
from alpha_system.scoring.engine import NameScore
from alpha_system.sizing.allocate import allocate_tranche, select_eligible


def _score(
    ticker: str,
    weight_input: float,
    *,
    sector: str = "",
    eligible: bool = True,
) -> NameScore:
    return NameScore(
        ticker=ticker,
        name=ticker,
        factors={},
        total_score=weight_input,
        eligibility=eligible,
        weight_input=weight_input if eligible else 0.0,
        eligibility_reason="test",
        sector=sector,
    )


def test_sector_cap_keeps_top_two_per_group() -> None:
    scores = [
        _score("A", 100, sector="bank"),
        _score("B", 90, sector="bank"),
        _score("C", 80, sector="bank"),  # 3rd bank — skip
        _score("D", 70, sector="auto"),
        _score("E", 60, sector="auto"),
        _score("F", 50, sector="chem"),
    ]
    selected, warnings = select_eligible(
        scores, target_names=6, max_names_per_sector=2
    )
    tickers = [s.ticker for s in selected]
    assert tickers == ["A", "B", "D", "E", "F"]
    assert "C" not in tickers
    assert any("sector cap" in w for w in warnings)


def test_sector_cap_shortfall_does_not_force_fill(cfg=None) -> None:
    cfg = cfg or load_config()
    # All eligible but same sector → only 2 selected vs target_names
    scores = [_score(chr(ord("A") + i), 100 - i, sector="bank") for i in range(8)]
    result = allocate_tranche(
        cfg,
        tranche_id=TrancheId.T1,
        scores=scores,
        existing_weights={},
        tranche_budget=0.25,
    )
    assert result.eligible_count == 2
    assert result.shortfall_names == max(0, result.target_names - 2)
    assert {a.ticker for a in result.allocated} == {"A", "B"}
    assert any("shortfall" in w for w in result.warnings)


def test_unknown_sector_uses_per_ticker_bucket() -> None:
    scores = [
        _score("A", 100, sector=""),
        _score("B", 90, sector="unknown"),
        _score("C", 80, sector=""),
        _score("D", 70, sector="bank"),
        _score("E", 60, sector="bank"),
        _score("F", 50, sector="bank"),
    ]
    selected, _ = select_eligible(scores, target_names=6, max_names_per_sector=2)
    tickers = [s.ticker for s in selected]
    # A/B/C each get own unknown bucket; bank capped at 2
    assert "A" in tickers and "B" in tickers and "C" in tickers
    assert "D" in tickers and "E" in tickers
    assert "F" not in tickers


def test_ineligible_never_selected_under_sector_pressure() -> None:
    scores = [
        _score("A", 100, sector="bank"),
        _score("B", 90, sector="bank"),
        _score("C", 80, sector="bank", eligible=False),
        _score("D", 70, sector="bank", eligible=False),
    ]
    selected, _ = select_eligible(scores, target_names=6, max_names_per_sector=2)
    assert [s.ticker for s in selected] == ["A", "B"]


def test_financial_bank_rolls_into_financial_cap() -> None:
    """은행(financial_bank)과 금융지주(financial)는 같은 테마 캡."""
    scores = [
        _score("316140", 100, sector="financial"),  # 우리금융
        _score("105560", 90, sector="financial"),  # KB
        _score("024110", 80, sector="financial_bank"),  # 기업은행 — 3번째 금융
        _score("000660", 70, sector="semiconductor"),
        _score("006040", 60, sector="consumer_staples"),
    ]
    selected, warnings = select_eligible(
        scores, target_names=8, max_names_per_sector=2
    )
    tickers = [s.ticker for s in selected]
    assert tickers == ["316140", "105560", "000660", "006040"]
    assert "024110" not in tickers
    assert any("sector cap" in w for w in warnings)


def test_insurance_rolls_into_financial_cap() -> None:
    """손보(insurance)도 금융 테마 캡에 합산 — KB+우리+DB 3종 불가."""
    scores = [
        _score("316140", 100, sector="financial"),
        _score("105560", 90, sector="financial"),
        _score("005830", 80, sector="insurance"),  # DB손보 — 3번째 금융 테마
        _score("000660", 70, sector="semiconductor"),
    ]
    selected, warnings = select_eligible(
        scores, target_names=8, max_names_per_sector=2
    )
    tickers = [s.ticker for s in selected]
    assert tickers == ["316140", "105560", "000660"]
    assert "005830" not in tickers
    assert any("sector cap" in w for w in warnings)


def test_sector_weight_cap_35_scales_two_names() -> None:
    """동일 섹터 2종 · 예산 50% → 종목캡 25%×2=50%이지만 섹터합 ≤35%."""
    cfg = load_config()
    scores = [
        _score("A", 100, sector="bank"),
        _score("B", 100, sector="bank"),
    ]
    result = allocate_tranche(
        cfg,
        tranche_id=TrancheId.T1,
        scores=scores,
        existing_weights={},
        tranche_budget=0.50,
    )
    sector_sum = sum(a.incremental_weight for a in result.allocated)
    assert sector_sum <= 0.35 + 1e-9
    assert result.unallocated_weight >= 0.15 - 1e-6
    assert any("sector_weight_cap" in w for w in result.warnings)
