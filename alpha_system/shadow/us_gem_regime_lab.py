"""미국 ETF(GEM 정석) · 금리/긴축 국면 검증 Lab (Review-only).

국내 대리(360750·195970…)와 분리 · Yahoo adjclose · Soft/target 불변.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from alpha_system.economy_compass.stage_history import build_stage_history
from alpha_system.shadow import household_alloc_lab as hh
from alpha_system.shadow import household_regime_lab as reg
from alpha_system.shadow.us_etf_prices import build_us_price_panel, norm_us_ticker

REPORT_REL = Path("data") / "local" / "us_gem_regime_lab_report.json"
COST_BPS = 5.0  # 미국 ETF 편도 근사(국내 Lab 15bp와 구분)

# GEM 정석 + 정적 대조 (검증 전용 · 운영 yaml 아님)
US_STRATEGIES: list[dict[str, Any]] = [
    {
        "id": "dual_efa",
        "kind": "dual_momentum",
        "name_ko": "듀얼 GEM · SPY vs EFA",
        "source": "Antonacci GEM · EFA(EAFE)",
        "lookback_months": 12,
        "offensive": [
            {"ticker": "SPY", "name": "SPY"},
            {"ticker": "EFA", "name": "EFA"},
        ],
        "cash_ticker": "BIL",
        "cash_name": "BIL",
        "safe_ticker": "AGG",
        "safe_name": "AGG",
    },
    {
        "id": "dual_vxus",
        "kind": "dual_momentum",
        "name_ko": "듀얼 GEM · SPY vs VXUS",
        "source": "Antonacci GEM · VXUS(ACWI ex-US)",
        "lookback_months": 12,
        "offensive": [
            {"ticker": "SPY", "name": "SPY"},
            {"ticker": "VXUS", "name": "VXUS"},
        ],
        "cash_ticker": "BIL",
        "cash_name": "BIL",
        "safe_ticker": "AGG",
        "safe_name": "AGG",
    },
    {
        "id": "sixty_forty_us",
        "kind": "static",
        "name_ko": "60/40 · SPY/AGG",
        "source": "미국 ETF 정적 대조",
        "rebalance": "annual_jan",
        "sleeves": [
            {"ticker": "SPY", "name": "SPY", "pct": 60},
            {"ticker": "AGG", "name": "AGG", "pct": 40},
        ],
    },
    {
        "id": "permanent_us",
        "kind": "static",
        "name_ko": "영구 · SPY/TLT/BIL/GLD",
        "source": "Permanent Portfolio 미국 ETF",
        "rebalance": "annual_jan",
        "sleeves": [
            {"ticker": "SPY", "name": "SPY", "pct": 25},
            {"ticker": "TLT", "name": "TLT", "pct": 25},
            {"ticker": "BIL", "name": "BIL", "pct": 25},
            {"ticker": "GLD", "name": "GLD", "pct": 25},
        ],
    },
    {
        "id": "spy_buyhold",
        "kind": "static",
        "name_ko": "SPY 바이홀드",
        "source": "지수·주식 벤치",
        "rebalance": "annual_jan",
        "sleeves": [{"ticker": "SPY", "name": "SPY", "pct": 100}],
    },
]

_CAVEATS = (
    "미국 상장 ETF Yahoo adjclose · 배당 재투자 근사 · 국내 대리와 성과 다름",
    "국면 정의=가계 국면 Lab과 동일(DFII10·DFF·stage·2022~)",
    "검증 전용 · Soft·target·운영 yaml 불변 · Review-only",
)


@dataclass
class UsGemRegimeReport:
    ok: bool
    as_of: str
    review_only: bool = True
    writes_target: bool = False
    definitions_ko: dict[str, str] = field(
        default_factory=lambda: dict(reg.REGIME_META)
    )
    caveats: list[str] = field(default_factory=list)
    strategies: list[reg.StrategyRegimeRow] = field(default_factory=list)
    rate_as_of: str = ""
    stage_ok: bool = False
    price_start: str = ""
    price_end: str = ""
    notes_ko: str = (
        "미국 ETF GEM 검증 · dual_efa≈국내 EAFE 근사 · dual_vxus=정식 ex-US"
    )


def report_path(root: Path) -> Path:
    return Path(root) / REPORT_REL


def _collect_tickers(strategies: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for st in strategies:
        if st.get("kind") == "static":
            for sl in st.get("sleeves") or []:
                tk = norm_us_ticker(sl.get("ticker"))
                if tk:
                    out.append(tk)
        else:
            for key in ("cash_ticker", "safe_ticker"):
                tk = norm_us_ticker(st.get(key))
                if tk:
                    out.append(tk)
            for off in st.get("offensive") or []:
                tk = norm_us_ticker(off.get("ticker") if isinstance(off, dict) else None)
                if tk:
                    out.append(tk)
    return list(dict.fromkeys(out))


def build_us_strategy_curves(
    root: Path,
    *,
    ensure_fetch: bool = True,
    injected_panel: pd.DataFrame | None = None,
    strategies: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, pd.Series], dict[str, str], pd.DataFrame]:
    stgs = list(strategies or US_STRATEGIES)
    tickers = _collect_tickers(stgs)
    panel = build_us_price_panel(
        root, tickers, ensure_fetch=ensure_fetch, injected=injected_panel
    )
    curves: dict[str, pd.Series] = {}
    reasons: dict[str, str] = {}
    for st in stgs:
        sid = str(st.get("id") or "")
        kind = str(st.get("kind") or "")
        if kind == "static":
            w = hh._merge_static_weights(list(st.get("sleeves") or []))
            # US tickers already alpha — re-key with us norm
            w = {norm_us_ticker(k): float(v) for k, v in w.items() if norm_us_ticker(k)}
            annual = str(st.get("rebalance") or "annual_jan").startswith("annual")
            curve, reason = hh._run_static(
                panel, w, cost_bps=COST_BPS, annual=annual
            )
        else:
            # dual recipe with US tickers (norm_ticker keeps letters)
            st_us = dict(st)
            st_us["cash_ticker"] = norm_us_ticker(st.get("cash_ticker"))
            st_us["safe_ticker"] = norm_us_ticker(st.get("safe_ticker"))
            st_us["offensive"] = [
                {
                    **o,
                    "ticker": norm_us_ticker(o.get("ticker")),
                }
                for o in (st.get("offensive") or [])
                if isinstance(o, dict)
            ]
            curve, reason = hh._run_dual_momentum(panel, st_us, cost_bps=COST_BPS)
        if curve.empty or reason:
            reasons[sid] = reason or "empty_curve"
        else:
            curves[sid] = curve
    return curves, reasons, panel


def run_us_gem_regime_lab(
    root: Path,
    *,
    ensure_fetch: bool = True,
    injected_panel: pd.DataFrame | None = None,
    injected_rates: Mapping[str, pd.Series] | None = None,
    injected_stages: pd.Series | None = None,
) -> UsGemRegimeReport:
    root = Path(root)
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    curves, reasons, panel = build_us_strategy_curves(
        root, ensure_fetch=ensure_fetch, injected_panel=injected_panel
    )
    real, dff, rate_note = reg.load_rate_levels(
        root, ensure_fetch=ensure_fetch, injected=injected_rates
    )
    if injected_stages is not None:
        stages = injected_stages
        stage_ok = not stages.empty
    else:
        board = build_stage_history(root, ensure_fetch=ensure_fetch)
        stages = board.stages if board.ok else pd.Series(dtype="Int64")
        stage_ok = bool(board.ok)

    name_by = {
        str(s["id"]): (str(s.get("name_ko") or s["id"]), str(s.get("kind") or ""))
        for s in US_STRATEGIES
    }
    rows: list[reg.StrategyRegimeRow] = []
    for sid, curve in curves.items():
        name, kind = name_by.get(sid, (sid, ""))
        idx = pd.DatetimeIndex(curve.index)
        slices = [
            reg._kpi_contiguous(curve, regime="full"),
            reg._kpi_contiguous(
                curve.loc[curve.index >= pd.Timestamp(reg.HIKE_START)],
                regime="since_2022",
            ),
            reg._kpi_spliced(
                curve,
                reg._mask_from_level(idx, real, ge=reg.REAL_HIGH, lt=None),
                regime="high_real",
            ),
            reg._kpi_spliced(
                curve,
                reg._mask_from_level(idx, real, ge=None, lt=reg.REAL_HIGH),
                regime="low_real",
            ),
            reg._kpi_spliced(
                curve,
                reg._mask_from_level(idx, dff, ge=reg.FED_HIGH, lt=None),
                regime="high_fed",
            ),
            reg._kpi_spliced(
                curve,
                reg._mask_from_stage(idx, stages, ge=reg.TIGHT_STAGE),
                regime="tight",
            ),
        ]
        rows.append(
            reg.StrategyRegimeRow(
                id=sid, name_ko=name, kind=kind, ok=True, slices=slices
            )
        )
    for sid, reason in reasons.items():
        if sid in curves:
            continue
        name, kind = name_by.get(sid, (sid, ""))
        rows.append(
            reg.StrategyRegimeRow(
                id=sid, name_ko=name, kind=kind, ok=False, reason=reason
            )
        )

    rate_as = ""
    if not real.empty:
        rate_as = str(pd.Timestamp(real.index[-1]).date())
    elif not dff.empty:
        rate_as = str(pd.Timestamp(dff.index[-1]).date())

    p_start = str(panel.index[0].date()) if len(panel.index) else ""
    p_end = str(panel.index[-1].date()) if len(panel.index) else ""

    return UsGemRegimeReport(
        ok=sum(1 for r in rows if r.ok) > 0,
        as_of=as_of,
        writes_target=False,
        caveats=list(_CAVEATS) + [f"금리시계열={rate_note}"],
        strategies=rows,
        rate_as_of=rate_as,
        stage_ok=stage_ok,
        price_start=p_start,
        price_end=p_end,
    )


def save_report(root: Path, report: UsGemRegimeReport) -> Path:
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
        "rate_as_of": report.rate_as_of,
        "stage_ok": report.stage_ok,
        "price_start": report.price_start,
        "price_end": report.price_end,
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


def us_gem_regime_table_html(report: UsGemRegimeReport | Mapping[str, Any]) -> str:
    html = reg.household_regime_table_html(
        report
        if isinstance(report, Mapping)
        else {
            "as_of": report.as_of,
            "notes_ko": report.notes_ko,
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
        },
        focus=("full", "since_2022", "high_real", "high_fed", "low_real", "tight"),
    )
    # title tweak
    return html.replace(
        "가계 Lab · 금리/긴축 국면 슬라이스 (Review-only)",
        "미국 ETF GEM 검증 · 금리/긴축 국면 (Review-only)",
        1,
    )


__all__ = [
    "US_STRATEGIES",
    "UsGemRegimeReport",
    "build_us_strategy_curves",
    "load_report",
    "report_path",
    "run_us_gem_regime_lab",
    "save_report",
    "us_gem_regime_table_html",
]
