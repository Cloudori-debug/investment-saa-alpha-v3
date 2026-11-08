"""가계 Lab · 금리/긴축 국면 슬라이스 KPI (Review-only · target 불변).

정의(고정 · 재최적화 금지):
- high_real: DFII10(실질10Y) ≥ 1.0% · economy_signal score_real_yield 스트레스 시작과 동일
- high_fed: DFF(연준금리) ≥ 3.0% · 정책금리 고금리 근사
- tight: FRED 5축 stage ≥ 4
- since_2022: 2022-01-01 이후 연속 구간(긴축 사이클 달력 근사)
- low_real: DFII10 < 1.0% · 대조

끊긴 국면일: 해당일 수익률만 이어 붙여 거래일 CAGR · Soft/target 불변.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from alpha_system.economy_compass.stage_history import (
    _resolve_fred_key,
    build_stage_history,
    fetch_fred_series_long,
    stage_asof,
)
from alpha_system.economy_signal import SERIES_DFF, SERIES_DFII10
from alpha_system.shadow.household_alloc_lab import build_strategy_curves

REPORT_REL = Path("data") / "local" / "household_regime_lab_report.json"
RATES_REL = Path("data") / "local" / "fred_rate_levels.csv"

REAL_HIGH = 1.0
FED_HIGH = 3.0
TIGHT_STAGE = 4
MIN_DAYS = 60
HIKE_START = "2022-01-01"

_CAVEATS = (
    "국면= FRED DFII10·DFF·stage · 국내 ETF NAV에 사후 슬라이스",
    "끊긴 국면일은 수익률만 이어 붙임(달력 CAGR과 다름) · since_2022만 연속 NAV",
    "고금리=실질≥1% 또는 연준≥3% 근사 · Soft·target 자동변경 없음 · Review-only",
)

REGIME_META: dict[str, str] = {
    "full": "전체 표본",
    "since_2022": "2022-01~ (긴축 사이클 달력)",
    "high_real": "실질금리 DFII10≥1%",
    "low_real": "실질금리 DFII10<1% (대조)",
    "high_fed": "연준 DFF≥3%",
    "tight": "나침반 stage≥4",
}


@dataclass
class SliceKpi:
    regime: str
    label_ko: str
    ok: bool
    cagr: float | None = None
    max_drawdown: float | None = None
    total_ret: float | None = None
    n_days: int = 0
    start: str = ""
    end: str = ""
    reason: str = ""


@dataclass
class StrategyRegimeRow:
    id: str
    name_ko: str
    kind: str
    ok: bool
    slices: list[SliceKpi] = field(default_factory=list)
    reason: str = ""


@dataclass
class HouseholdRegimeLabReport:
    ok: bool
    as_of: str
    review_only: bool = True
    writes_target: bool = False
    definitions_ko: dict[str, str] = field(default_factory=lambda: dict(REGIME_META))
    caveats: list[str] = field(default_factory=list)
    strategies: list[StrategyRegimeRow] = field(default_factory=list)
    rate_as_of: str = ""
    stage_ok: bool = False
    notes_ko: str = (
        "지금 같은 고금리 ≈ high_real · high_fed · since_2022 를 full·low_real 과 비교"
    )


def report_path(root: Path) -> Path:
    return Path(root) / REPORT_REL


def _cagr_calendar(equity: pd.Series) -> float | None:
    if len(equity) < 2:
        return None
    start = float(equity.iloc[0])
    end = float(equity.iloc[-1])
    if start <= 0 or end <= 0:
        return None
    days = (equity.index[-1] - equity.index[0]).days
    if days < 30:
        return None
    return float((end / start) ** (365.25 / days) - 1.0)


def _cagr_trading(equity: pd.Series) -> float | None:
    if len(equity) < MIN_DAYS:
        return None
    end = float(equity.iloc[-1])
    if end <= 0:
        return None
    n = int(len(equity))
    return float(end ** (252.0 / n) - 1.0)


def _max_dd(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    return float((equity / peak - 1.0).min())


def _kpi_contiguous(equity: pd.Series, *, regime: str) -> SliceKpi:
    label = REGIME_META.get(regime, regime)
    if equity.empty or len(equity) < MIN_DAYS:
        return SliceKpi(
            regime=regime,
            label_ko=label,
            ok=False,
            n_days=int(len(equity)),
            reason="표본부족",
        )
    return SliceKpi(
        regime=regime,
        label_ko=label,
        ok=True,
        cagr=_cagr_calendar(equity),
        max_drawdown=_max_dd(equity),
        total_ret=float(equity.iloc[-1] / equity.iloc[0] - 1.0),
        n_days=int(len(equity)),
        start=str(equity.index[0].date()),
        end=str(equity.index[-1].date()),
    )


def _kpi_spliced(equity: pd.Series, mask: pd.Series, *, regime: str) -> SliceKpi:
    label = REGIME_META.get(regime, regime)
    m = mask.reindex(equity.index).fillna(False).astype(bool)
    if int(m.sum()) < MIN_DAYS:
        return SliceKpi(
            regime=regime,
            label_ko=label,
            ok=False,
            n_days=int(m.sum()),
            reason="표본부족",
        )
    rets = equity.pct_change().fillna(0.0).loc[m]
    curve = (1.0 + rets).cumprod()
    if curve.empty:
        return SliceKpi(
            regime=regime, label_ko=label, ok=False, reason="empty_slice"
        )
    return SliceKpi(
        regime=regime,
        label_ko=label,
        ok=True,
        cagr=_cagr_trading(curve),
        max_drawdown=_max_dd(curve),
        total_ret=float(curve.iloc[-1] - 1.0),
        n_days=int(len(curve)),
        start=str(rets.index[0].date()),
        end=str(rets.index[-1].date()),
    )


def _load_rate_cache(root: Path) -> tuple[pd.Series, pd.Series]:
    path = Path(root) / RATES_REL
    if not path.is_file():
        return pd.Series(dtype=float), pd.Series(dtype=float)
    try:
        df = pd.read_csv(path, parse_dates=["date"])
    except (OSError, ValueError):
        return pd.Series(dtype=float), pd.Series(dtype=float)
    if df.empty or "date" not in df.columns:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    df = df.set_index("date").sort_index()
    real = (
        pd.to_numeric(df["dfii10"], errors="coerce")
        if "dfii10" in df.columns
        else pd.Series(dtype=float)
    )
    dff = (
        pd.to_numeric(df["dff"], errors="coerce")
        if "dff" in df.columns
        else pd.Series(dtype=float)
    )
    return real.dropna(), dff.dropna()


def _save_rate_cache(root: Path, real: pd.Series, dff: pd.Series) -> None:
    path = Path(root) / RATES_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    idx = real.index.union(dff.index)
    if len(idx) == 0:
        return
    df = pd.DataFrame(
        {
            "date": pd.DatetimeIndex(idx),
            "dfii10": real.reindex(idx),
            "dff": dff.reindex(idx),
        }
    )
    try:
        df.to_csv(path, index=False, encoding="utf-8")
    except OSError:
        pass


def load_rate_levels(
    root: Path,
    *,
    ensure_fetch: bool = True,
    injected: Mapping[str, pd.Series] | None = None,
) -> tuple[pd.Series, pd.Series, str]:
    """DFII10 · DFF · as_of note."""
    if injected is not None:
        real = injected.get("real", pd.Series(dtype=float))
        dff = injected.get("dff", pd.Series(dtype=float))
        return real, dff, "injected"
    real, dff = _load_rate_cache(root)
    if not ensure_fetch and (not real.empty or not dff.empty):
        return real, dff, "cache"
    if ensure_fetch:
        key = _resolve_fred_key(root)
        fetched_real = pd.Series(dtype=float)
        fetched_dff = pd.Series(dtype=float)
        if key:
            try:
                fetched_real = fetch_fred_series_long(SERIES_DFII10, api_key=key)
                fetched_dff = fetch_fred_series_long(SERIES_DFF, api_key=key)
            except Exception:  # noqa: BLE001
                fetched_real = pd.Series(dtype=float)
                fetched_dff = pd.Series(dtype=float)
        if not fetched_real.empty:
            real = fetched_real
        if not fetched_dff.empty:
            dff = fetched_dff
        if not real.empty or not dff.empty:
            _save_rate_cache(root, real, dff)
            return real, dff, "fred" if key else "cache"
    if not real.empty or not dff.empty:
        return real, dff, "cache"
    return real, dff, "missing"


def _mask_from_level(
    index: pd.DatetimeIndex, level: pd.Series, *, ge: float | None, lt: float | None
) -> pd.Series:
    if level.empty:
        return pd.Series(False, index=index)
    # asof forward: map each day to latest known level
    lv = level.sort_index()
    aligned = lv.reindex(lv.index.union(index)).sort_index().ffill().reindex(index)
    out = pd.Series(False, index=index)
    if ge is not None:
        out = aligned >= float(ge)
    if lt is not None:
        out = aligned < float(lt)
    return out.fillna(False).astype(bool)


def _mask_from_stage(index: pd.DatetimeIndex, stages: pd.Series, *, ge: int) -> pd.Series:
    if stages is None or stages.empty:
        return pd.Series(False, index=index)
    flags: list[bool] = []
    for dt in index:
        st = stage_asof(stages, pd.Timestamp(dt))
        flags.append(st is not None and int(st) >= int(ge))
    return pd.Series(flags, index=index)


def run_household_regime_lab(
    root: Path,
    *,
    ensure_fetch: bool = True,
    injected_panel: pd.DataFrame | None = None,
    injected_rates: Mapping[str, pd.Series] | None = None,
    injected_stages: pd.Series | None = None,
) -> HouseholdRegimeLabReport:
    root = Path(root)
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    curves, reasons, raw = build_strategy_curves(
        root, ensure_fetch=ensure_fetch, injected_panel=injected_panel
    )
    real, dff, rate_note = load_rate_levels(
        root, ensure_fetch=ensure_fetch, injected=injected_rates
    )
    if injected_stages is not None:
        stages = injected_stages
        stage_ok = not stages.empty
    else:
        board = build_stage_history(root, ensure_fetch=ensure_fetch)
        stages = board.stages if board.ok else pd.Series(dtype="Int64")
        stage_ok = bool(board.ok)

    rows: list[StrategyRegimeRow] = []
    name_by: dict[str, tuple[str, str]] = {}
    if raw is not None:
        for st in raw.get("strategies") or []:
            if isinstance(st, dict) and st.get("id"):
                name_by[str(st["id"])] = (
                    str(st.get("name_ko") or st["id"]),
                    str(st.get("kind") or ""),
                )

    for sid, curve in curves.items():
        name, kind = name_by.get(sid, (sid, ""))
        idx = pd.DatetimeIndex(curve.index)
        slices = [
            _kpi_contiguous(curve, regime="full"),
            _kpi_contiguous(
                curve.loc[curve.index >= pd.Timestamp(HIKE_START)],
                regime="since_2022",
            ),
            _kpi_spliced(
                curve,
                _mask_from_level(idx, real, ge=REAL_HIGH, lt=None),
                regime="high_real",
            ),
            _kpi_spliced(
                curve,
                _mask_from_level(idx, real, ge=None, lt=REAL_HIGH),
                regime="low_real",
            ),
            _kpi_spliced(
                curve,
                _mask_from_level(idx, dff, ge=FED_HIGH, lt=None),
                regime="high_fed",
            ),
            _kpi_spliced(
                curve,
                _mask_from_stage(idx, stages, ge=TIGHT_STAGE),
                regime="tight",
            ),
        ]
        rows.append(
            StrategyRegimeRow(
                id=sid, name_ko=name, kind=kind, ok=True, slices=slices
            )
        )
    for sid, reason in reasons.items():
        if sid in curves or sid == "_":
            continue
        name, kind = name_by.get(sid, (sid, ""))
        rows.append(
            StrategyRegimeRow(
                id=sid, name_ko=name, kind=kind, ok=False, reason=reason
            )
        )

    rate_as = ""
    if not real.empty:
        rate_as = str(pd.Timestamp(real.index[-1]).date())
    elif not dff.empty:
        rate_as = str(pd.Timestamp(dff.index[-1]).date())

    ok_n = sum(1 for r in rows if r.ok)
    return HouseholdRegimeLabReport(
        ok=ok_n > 0,
        as_of=as_of,
        writes_target=False,
        caveats=list(_CAVEATS) + [f"금리시계열={rate_note}"],
        strategies=rows,
        rate_as_of=rate_as,
        stage_ok=stage_ok,
    )


def save_report(root: Path, report: HouseholdRegimeLabReport) -> Path:
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


def household_regime_table_html(
    report: HouseholdRegimeLabReport | Mapping[str, Any],
    *,
    focus: tuple[str, ...] = ("full", "since_2022", "high_real", "high_fed", "low_real"),
) -> str:
    from html import escape

    if isinstance(report, HouseholdRegimeLabReport):
        rows = report.strategies
        caveats = report.caveats
        as_of = report.as_of
        notes = report.notes_ko
        defs = report.definitions_ko
    else:
        rows = list(report.get("strategies") or [])
        caveats = list(report.get("caveats") or [])
        as_of = str(report.get("as_of") or "")
        notes = str(report.get("notes_ko") or "")
        defs = dict(report.get("definitions_ko") or REGIME_META)

    head = "".join(f"<th>{escape(defs.get(r, r))}</th>" for r in focus)
    body: list[str] = []
    for s in rows:
        if isinstance(s, StrategyRegimeRow):
            d = {
                "name_ko": s.name_ko,
                "ok": s.ok,
                "reason": s.reason,
                "slices": [asdict(x) for x in s.slices],
            }
        else:
            d = dict(s)
        by = {
            str(x.get("regime")): x
            for x in (d.get("slices") or [])
            if isinstance(x, dict)
        }
        cells = []
        for r in focus:
            sl = by.get(r) or {}
            if not d.get("ok"):
                cells.append(f"<td>{escape(str(d.get('reason') or '실패')[:28])}</td>")
                continue
            if not sl.get("ok"):
                cells.append(
                    f"<td class='pf-env-muted'>{escape(str(sl.get('reason') or '—'))}</td>"
                )
                continue
            cagr = sl.get("cagr")
            mdd = sl.get("max_drawdown")
            cagr_s = "—" if cagr is None else f"{100.0 * float(cagr):+.1f}%"
            mdd_s = "—" if mdd is None else f"{100.0 * float(mdd):.1f}%"
            cells.append(f"<td>{cagr_s} / {mdd_s}</td>")
        body.append(
            "<tr>"
            f"<td>{escape(str(d.get('name_ko') or ''))}</td>"
            + "".join(cells)
            + "</tr>"
        )
    tip = " · ".join(escape(c) for c in caveats[:3])
    def_line = " · ".join(f"{escape(k)}={escape(v)}" for k, v in list(defs.items())[:4])
    return (
        '<div class="pf-hh-lab" role="region" aria-label="가계 국면 Lab">'
        '<div class="pf-hh-k">가계 Lab · 금리/긴축 국면 슬라이스 (Review-only)</div>'
        f'<div class="pf-env-muted">as_of {escape(as_of)} · {escape(notes)}</div>'
        f'<div class="pf-env-muted">{def_line}</div>'
        "<table class='pf-hh-lab-table'><thead><tr>"
        "<th>전략</th>"
        + head
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
        f'<div class="pf-hh-tip">{tip}</div>'
        "</div>"
    )


__all__ = [
    "HouseholdRegimeLabReport",
    "REGIME_META",
    "household_regime_table_html",
    "load_report",
    "load_rate_levels",
    "report_path",
    "run_household_regime_lab",
    "save_report",
]
