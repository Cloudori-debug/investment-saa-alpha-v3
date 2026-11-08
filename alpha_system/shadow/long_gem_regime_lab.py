"""장기(1926~) 월간 GEM/절대모멘텀 국면 Lab · Ken French (Review-only).

ETF Lab(~2007~)과 분리. 대공황 구간은 미국 절대모멘텀으로만 가능
(선진 ex-US 월간은 1990-07~). Soft/target 불변.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from alpha_system.economy_compass.stage_history import build_stage_history
from alpha_system.shadow import household_regime_lab as reg
from alpha_system.shadow.ff_monthly import (
    bill_total_return_index,
    equity_total_return_index,
    load_ff_dev_exus_monthly,
    load_ff_us_monthly,
)
from alpha_system.shadow.household_alloc_lab import _apply_cost

REPORT_REL = Path("data") / "local" / "long_gem_regime_lab_report.json"
COST_BPS = 5.0
LOOKBACK_M = 12
MIN_MONTHS = 24


def _mom_ret_monthly(
    panel: pd.DataFrame, ticker: str, i: int, months: int
) -> float | None:
    """월말 패널 · i번째 행 기준 lookback개월 수익률."""
    if ticker not in panel.columns or i < int(months):
        return None
    end_px = float(panel[ticker].iloc[i])
    start_px = float(panel[ticker].iloc[i - int(months)])
    if start_px <= 0 or end_px <= 0:
        return None
    return end_px / start_px - 1.0

# 대공황·고금리 달력 창
DEPRESSION_CORE = ("1929-09-01", "1933-03-31")  # 폭락~은행휴업 근사
DEPRESSION_DECADE = ("1929-01-01", "1939-12-31")
HIKE_70S = ("1972-01-01", "1982-12-31")  # 고금리·스태그 근사

_CAVEATS = (
    "Ken French 월간(미국 1926-07~ · Dev ex-US 1990-07~) · ETF/Yahoo와 별개",
    "대공황=미국 절대모멘텀(주식 vs T-bill) · 상대(미 vs 비미)는 1990~만",
    "안전자산=T-bill(RF) · AGG 장기 총수익 시계열 부재 · Soft·target 불변",
)

REGIME_META: dict[str, str] = {
    **reg.REGIME_META,
    "depression_core": "대공황 핵심(1929-09~1933-03)",
    "depression_decade": "대공황 전후(1929~1939)",
    "hike_70s": "1970s 고금리(1972~1982)",
    "high_bill": "T-bill 연율≥3%(RF×12)",
}


@dataclass
class LongGemReport:
    ok: bool
    as_of: str
    review_only: bool = True
    writes_target: bool = False
    definitions_ko: dict[str, str] = field(default_factory=lambda: dict(REGIME_META))
    caveats: list[str] = field(default_factory=list)
    strategies: list[reg.StrategyRegimeRow] = field(default_factory=list)
    sample_start: str = ""
    sample_end: str = ""
    notes_ko: str = (
        "장기 월간 · 대공황은 abs_us · 상대 GEM은 dual_exus(1990~)"
    )


def report_path(root: Path) -> Path:
    return Path(root) / REPORT_REL


def _run_dual_monthly(
    panel: pd.DataFrame,
    *,
    offensive: list[str],
    cash: str,
    safe: str,
    lookback: int = LOOKBACK_M,
    cost_bps: float = COST_BPS,
) -> tuple[pd.Series, str]:
    need = list(dict.fromkeys(t for t in [*offensive, cash, safe] if t))
    cols = [c for c in need if c in panel.columns]
    if len(cols) < 2:
        return pd.Series(dtype=float), "dual_missing_prices"
    sub = panel.loc[:, cols].dropna(how="any")
    if len(sub) < MIN_MONTHS:
        return pd.Series(dtype=float), "dual_insufficient_history"
    rets = sub.pct_change().fillna(0.0)
    equity = 1.0
    curve: list[tuple[pd.Timestamp, float]] = []
    hold = safe or cash
    w_cur = {hold: 1.0}
    dates = list(rets.index)
    for i, dt in enumerate(dates):
        row = rets.iloc[i]
        if i > 0:
            cash_m = _mom_ret_monthly(sub, cash, i, lookback) if cash else None
            mom = {o: _mom_ret_monthly(sub, o, i, lookback) for o in offensive}
            if cash_m is None or any(r is None for r in mom.values()):
                new_hold = safe or cash
            else:
                best = max(offensive, key=lambda o: float(mom[o]))  # type: ignore[arg-type]
                best_r = float(mom[best])  # type: ignore[index]
                new_hold = best if best_r > cash_m else (safe or cash)
            if new_hold != hold:
                new_w = {new_hold: 1.0}
                equity *= 1.0 - _apply_cost(w_cur, new_w, cost_bps)
                w_cur = new_w
                hold = new_hold
            try:
                day_ret = float(row[hold])
            except (KeyError, TypeError, ValueError):
                day_ret = 0.0
            if day_ret != day_ret:  # NaN
                day_ret = 0.0
            equity *= 1.0 + day_ret
        curve.append((dt, equity))
    return pd.Series({d: v for d, v in curve}).sort_index(), ""


def _buyhold(panel: pd.DataFrame, ticker: str) -> tuple[pd.Series, str]:
    if ticker not in panel.columns:
        return pd.Series(dtype=float), "missing"
    s = panel[ticker].dropna()
    if len(s) < MIN_MONTHS:
        return pd.Series(dtype=float), "short"
    return (s / float(s.iloc[0])), ""


def _mask_high_bill(index: pd.DatetimeIndex, rf_pct: pd.Series) -> pd.Series:
    """RF monthly % · 연율 근사 rf*12 ≥ 3."""
    if rf_pct.empty:
        return pd.Series(False, index=index)
    lv = rf_pct.sort_index()
    aligned = lv.reindex(lv.index.union(index)).sort_index().ffill().reindex(index)
    return ((aligned * 12.0) >= 3.0).fillna(False)


def _cagr_months(equity: pd.Series) -> float | None:
    if len(equity) < 6:
        return None
    start = float(equity.iloc[0])
    end = float(equity.iloc[-1])
    if start <= 0 or end <= 0:
        return None
    years = len(equity) / 12.0
    if years < 0.5:
        return None
    return float((end / start) ** (1.0 / years) - 1.0)


def _mdd(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    return float((equity / peak - 1.0).min())


def _window_kpi(curve: pd.Series, start: str, end: str, *, regime: str) -> reg.SliceKpi:
    """월간 창 · MIN 6개월 (일봉 Lab의 60거래일 임계와 분리)."""
    label = REGIME_META.get(regime, regime)
    sub = curve.loc[(curve.index >= pd.Timestamp(start)) & (curve.index <= pd.Timestamp(end))]
    if len(sub) < 6:
        return reg.SliceKpi(
            regime=regime, label_ko=label, ok=False, n_days=int(len(sub)), reason="표본부족"
        )
    sub = sub / float(sub.iloc[0])
    return reg.SliceKpi(
        regime=regime,
        label_ko=label,
        ok=True,
        cagr=_cagr_months(sub),
        max_drawdown=_mdd(sub),
        total_ret=float(sub.iloc[-1] / sub.iloc[0] - 1.0),
        n_days=int(len(sub)),
        start=str(sub.index[0].date()),
        end=str(sub.index[-1].date()),
    )


def _full_monthly_kpi(curve: pd.Series) -> reg.SliceKpi:
    if len(curve) < MIN_MONTHS:
        return reg.SliceKpi(
            regime="full",
            label_ko=REGIME_META["full"],
            ok=False,
            n_days=int(len(curve)),
            reason="표본부족",
        )
    return reg.SliceKpi(
        regime="full",
        label_ko=REGIME_META["full"],
        ok=True,
        cagr=_cagr_months(curve),
        max_drawdown=_mdd(curve),
        total_ret=float(curve.iloc[-1] / curve.iloc[0] - 1.0),
        n_days=int(len(curve)),
        start=str(curve.index[0].date()),
        end=str(curve.index[-1].date()),
    )


def build_long_panels(
    root: Path, *, ensure_fetch: bool = True
) -> tuple[pd.DataFrame, pd.Series]:
    """wide: US, EXUS, BIL · RF% series for high_bill mask."""
    us = load_ff_us_monthly(root, ensure_fetch=ensure_fetch)
    dev = load_ff_dev_exus_monthly(root, ensure_fetch=ensure_fetch)
    if us.empty:
        return pd.DataFrame(), pd.Series(dtype=float)
    us_eq = equity_total_return_index(us)
    bil = bill_total_return_index(us)
    panel = pd.DataFrame({"US": us_eq, "BIL": bil}).dropna(how="any")
    if not dev.empty:
        ex = equity_total_return_index(dev)
        panel = panel.join(ex.rename("EXUS"), how="left")
    rf = us["RF"] if "RF" in us.columns else pd.Series(dtype=float)
    return panel, rf.reindex(panel.index).ffill()


def run_long_gem_regime_lab(
    root: Path,
    *,
    ensure_fetch: bool = True,
    injected_panel: pd.DataFrame | None = None,
    injected_rf: pd.Series | None = None,
    injected_rates: Mapping[str, pd.Series] | None = None,
    injected_stages: pd.Series | None = None,
) -> LongGemReport:
    root = Path(root)
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if injected_panel is not None and not injected_panel.empty:
        panel = injected_panel.sort_index()
        rf = (
            injected_rf
            if injected_rf is not None
            else pd.Series(0.2, index=panel.index)
        )
    else:
        panel, rf = build_long_panels(root, ensure_fetch=ensure_fetch)
    if panel.empty:
        return LongGemReport(
            ok=False,
            as_of=as_of,
            caveats=list(_CAVEATS) + ["FF 월간 로드 실패"],
        )

    real, dff, rate_note = reg.load_rate_levels(
        root, ensure_fetch=ensure_fetch, injected=injected_rates
    )
    if injected_stages is not None:
        stages = injected_stages
    else:
        board = build_stage_history(root, ensure_fetch=ensure_fetch)
        stages = board.stages if board.ok else pd.Series(dtype="Int64")

    def build_abs() -> tuple[pd.Series, str]:
        return _run_dual_monthly(
            panel, offensive=["US"], cash="BIL", safe="BIL"
        )

    def build_rel() -> tuple[pd.Series, str]:
        if "EXUS" not in panel.columns:
            return pd.Series(dtype=float), "exus_missing"
        sub = panel.dropna(subset=["US", "EXUS", "BIL"])
        return _run_dual_monthly(
            sub, offensive=["US", "EXUS"], cash="BIL", safe="BIL"
        )

    def build_us() -> tuple[pd.Series, str]:
        return _buyhold(panel, "US")

    def build_bil() -> tuple[pd.Series, str]:
        return _buyhold(panel, "BIL")

    builders = [
        ("abs_us", "절대모멘텀 US→Tbill", "dual_momentum", build_abs),
        ("dual_exus", "듀얼 GEM US vs DevExUS", "dual_momentum", build_rel),
        ("us_buyhold", "미국시장 바이홀드", "static", build_us),
        ("tbill_hold", "T-bill 홀드", "static", build_bil),
    ]

    rows: list[reg.StrategyRegimeRow] = []
    for sid, name, kind, fn in builders:
        curve, reason = fn()
        if curve.empty or reason:
            rows.append(
                reg.StrategyRegimeRow(
                    id=sid, name_ko=name, kind=kind, ok=False, reason=reason or "empty"
                )
            )
            continue
        idx = pd.DatetimeIndex(curve.index)
        since = curve.loc[curve.index >= pd.Timestamp(reg.HIKE_START)]
        since_kpi = (
            _full_monthly_kpi(since / float(since.iloc[0]))
            if len(since) >= 6
            else reg.SliceKpi(
                regime="since_2022",
                label_ko=REGIME_META["since_2022"],
                ok=False,
                reason="표본부족",
            )
        )
        since_kpi.regime = "since_2022"
        since_kpi.label_ko = REGIME_META["since_2022"]

        def _spliced_monthly(mask: pd.Series, *, regime: str) -> reg.SliceKpi:
            label = REGIME_META.get(regime, regime)
            m = mask.reindex(curve.index).fillna(False).astype(bool)
            if int(m.sum()) < 6:
                return reg.SliceKpi(
                    regime=regime,
                    label_ko=label,
                    ok=False,
                    n_days=int(m.sum()),
                    reason="표본부족",
                )
            rets = curve.pct_change().fillna(0.0).loc[m]
            sc = (1.0 + rets).cumprod()
            return reg.SliceKpi(
                regime=regime,
                label_ko=label,
                ok=True,
                cagr=_cagr_months(sc),
                max_drawdown=_mdd(sc),
                total_ret=float(sc.iloc[-1] - 1.0) if len(sc) else None,
                n_days=int(len(sc)),
                start=str(rets.index[0].date()),
                end=str(rets.index[-1].date()),
            )

        slices = [
            _full_monthly_kpi(curve),
            _window_kpi(curve, *DEPRESSION_CORE, regime="depression_core"),
            _window_kpi(curve, *DEPRESSION_DECADE, regime="depression_decade"),
            _window_kpi(curve, *HIKE_70S, regime="hike_70s"),
            since_kpi,
            _spliced_monthly(
                reg._mask_from_level(idx, real, ge=reg.REAL_HIGH, lt=None),
                regime="high_real",
            ),
            _spliced_monthly(
                reg._mask_from_level(idx, dff, ge=reg.FED_HIGH, lt=None),
                regime="high_fed",
            ),
            _spliced_monthly(_mask_high_bill(idx, rf), regime="high_bill"),
            _spliced_monthly(
                reg._mask_from_stage(idx, stages, ge=reg.TIGHT_STAGE),
                regime="tight",
            ),
        ]
        rows.append(
            reg.StrategyRegimeRow(
                id=sid, name_ko=name, kind=kind, ok=True, slices=slices
            )
        )

    return LongGemReport(
        ok=any(r.ok for r in rows),
        as_of=as_of,
        writes_target=False,
        caveats=list(_CAVEATS) + [f"금리시계열={rate_note}"],
        strategies=rows,
        sample_start=str(panel.index[0].date()),
        sample_end=str(panel.index[-1].date()),
        definitions_ko=dict(REGIME_META),
    )


def save_report(root: Path, report: LongGemReport) -> Path:
    path = report_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ok": report.ok,
        "as_of": report.as_of,
        "review_only": True,
        "writes_target": False,
        "definitions_ko": report.definitions_ko,
        "caveats": report.caveats,
        "notes_ko": report.notes_ko,
        "sample_start": report.sample_start,
        "sample_end": report.sample_end,
        "strategies": [
            {
                "id": s.id,
                "name_ko": s.name_ko,
                "kind": s.kind,
                "ok": s.ok,
                "reason": s.reason,
                "slices": [asdict(x) for x in s.slices],
            }
            for s in report.strategies
        ],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def load_report(root: Path) -> dict[str, Any] | None:
    path = report_path(root)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def long_gem_table_html(report: LongGemReport | Mapping[str, Any]) -> str:
    focus = (
        "full",
        "depression_core",
        "depression_decade",
        "hike_70s",
        "high_bill",
        "since_2022",
    )
    if isinstance(report, LongGemReport):
        payload: dict[str, Any] = {
            "as_of": report.as_of,
            "notes_ko": (
                f"{report.notes_ko} · 표본 {report.sample_start}→{report.sample_end}"
            ),
            "caveats": report.caveats,
            "definitions_ko": report.definitions_ko,
            "strategies": [
                {
                    "name_ko": s.name_ko,
                    "ok": s.ok,
                    "reason": s.reason,
                    "slices": [asdict(x) for x in s.slices],
                }
                for s in report.strategies
            ],
        }
    else:
        payload = dict(report)
        payload["notes_ko"] = (
            f"{payload.get('notes_ko') or ''} · 표본 "
            f"{payload.get('sample_start')}→{payload.get('sample_end')}"
        )
        payload["definitions_ko"] = dict(
            payload.get("definitions_ko") or REGIME_META
        )
    html = reg.household_regime_table_html(payload, focus=focus)
    return html.replace(
        "가계 Lab · 금리/긴축 국면 슬라이스 (Review-only)",
        "장기 월간 GEM · 대공황~ (Ken French · Review-only)",
        1,
    )


__all__ = [
    "LongGemReport",
    "REGIME_META",
    "load_report",
    "long_gem_table_html",
    "report_path",
    "run_long_gem_regime_lab",
    "save_report",
]
