"""가계 본체 Lab — 정적 배분 차용 + 듀얼모멘텀 근사 BT (Review-only).

A안 · 국내 ETF · Soft/target/Core score_m 불변 · writes_target=False.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd
import yaml

from alpha_system.proposal_chart import norm_ticker

RECIPES_REL = Path("data") / "household_static_alloc.yaml"
REPORT_REL = Path("data") / "local" / "household_alloc_lab_report.json"

_CAVEATS = (
    "국내상장·달러축 대리 · 원문 미국 ETF와 성과 다름",
    "배당·과세 단순화 · 편도 비용만 · (H)·선물 롤·합성 추적오차",
    "표본은 공통가격 겹침 구간(장기채 ETF 상장 후 짧을 수 있음)",
    "DBC 칸은 금 합산 등 근사 · Soft·target 자동변경 없음 · Review-only",
)


@dataclass
class AllocStrategyResult:
    id: str
    name_ko: str
    kind: str
    source: str
    ok: bool
    cagr: float | None = None
    max_drawdown: float | None = None
    total_ret: float | None = None
    n_days: int = 0
    start: str = ""
    end: str = ""
    reason: str = ""
    tickers: list[str] = field(default_factory=list)


@dataclass
class HouseholdAllocLabReport:
    ok: bool
    as_of: str
    review_only: bool = True
    writes_target: bool = False
    cost_bps_one_way: float = 15.0
    caveats: list[str] = field(default_factory=list)
    strategies: list[AllocStrategyResult] = field(default_factory=list)
    notes_ko: str = ""


def recipes_path(root: Path) -> Path:
    return Path(root) / RECIPES_REL


def report_path(root: Path) -> Path:
    return Path(root) / REPORT_REL


def load_recipes(root: Path) -> dict[str, Any]:
    path = recipes_path(root)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("household_static_alloc.yaml invalid")
    return raw


def validate_recipes(raw: Mapping[str, Any]) -> list[str]:
    """Return human errors (empty = ok)."""
    errs: list[str] = []
    forbid = [str(x) for x in (raw.get("forbid_name_substrings") or [])]
    for st in raw.get("strategies") or []:
        if not isinstance(st, dict):
            errs.append("strategy not dict")
            continue
        sid = str(st.get("id") or "")
        kind = str(st.get("kind") or "")
        if kind == "static":
            sleeves = list(st.get("sleeves") or [])
            tot = 0.0
            for sl in sleeves:
                tot += float(sl.get("pct") or 0)
                name = str(sl.get("name") or "")
                for bad in forbid:
                    if bad and bad in name:
                        errs.append(f"{sid}: forbid name {name}")
                tk = norm_ticker(sl.get("ticker"))
                if not tk:
                    errs.append(f"{sid}: empty ticker")
            if abs(tot - 100.0) > 0.15:
                errs.append(f"{sid}: sleeve pct sum={tot}")
        elif kind == "dual_momentum":
            for key in ("cash_ticker", "safe_ticker"):
                if not norm_ticker(st.get(key)):
                    errs.append(f"{sid}: missing {key}")
            offs = list(st.get("offensive") or [])
            if len(offs) < 2:
                errs.append(f"{sid}: need 2 offensive")
        else:
            errs.append(f"{sid}: unknown kind {kind}")
    return errs


def _merge_static_weights(sleeves: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    w: dict[str, float] = {}
    for sl in sleeves:
        tk = norm_ticker(sl.get("ticker"))
        if not tk:
            continue
        w[tk] = w.get(tk, 0.0) + float(sl.get("pct") or 0.0) / 100.0
    s = sum(w.values())
    if s <= 0:
        return {}
    return {k: v / s for k, v in w.items()}


def collect_tickers(raw: Mapping[str, Any]) -> list[str]:
    out: list[str] = []
    for st in raw.get("strategies") or []:
        if not isinstance(st, dict):
            continue
        if str(st.get("kind")) == "static":
            for sl in st.get("sleeves") or []:
                tk = norm_ticker(sl.get("ticker"))
                if tk:
                    out.append(tk)
        elif str(st.get("kind")) == "dual_momentum":
            for key in ("cash_ticker", "safe_ticker"):
                tk = norm_ticker(st.get(key))
                if tk:
                    out.append(tk)
            for off in st.get("offensive") or []:
                tk = norm_ticker(off.get("ticker") if isinstance(off, dict) else None)
                if tk:
                    out.append(tk)
    return list(dict.fromkeys(out))


def _read_local_panel(root: Path, tickers: Sequence[str]) -> pd.DataFrame:
    """Wide close panel from proposal_replay_prices / prices_history if present."""
    paths = [
        Path(root) / "data" / "local" / "proposal_replay_prices.csv",
        Path(root) / "data" / "prices_history.csv",
        Path(root) / "data" / "local" / "household_alloc_prices.csv",
    ]
    frames: list[pd.DataFrame] = []
    need = {norm_ticker(t) for t in tickers}
    for path in paths:
        if not path.is_file():
            continue
        try:
            df = pd.read_csv(path, dtype=str)
        except (OSError, ValueError):
            continue
        if df.empty or "ticker" not in df.columns:
            continue
        date_col = "date" if "date" in df.columns else ("as_of" if "as_of" in df.columns else None)
        close_col = "close" if "close" in df.columns else None
        if not date_col or not close_col:
            continue
        df = df.copy()
        df["ticker"] = df["ticker"].map(norm_ticker)
        df = df[df["ticker"].isin(need)]
        if df.empty:
            continue
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df[close_col] = pd.to_numeric(df[close_col], errors="coerce")
        df = df.dropna(subset=[date_col, close_col])
        piv = df.pivot_table(
            index=date_col, columns="ticker", values=close_col, aggfunc="last"
        )
        frames.append(piv.sort_index())
    if not frames:
        return pd.DataFrame()
    panel = frames[0]
    for fr in frames[1:]:
        panel = panel.combine_first(fr)
    return panel.sort_index()


def _fetch_pykrx_panel(
    tickers: Sequence[str],
    *,
    start: str,
    end: str,
) -> pd.DataFrame:
    try:
        from pykrx import stock
    except ImportError:
        return pd.DataFrame()
    cols: dict[str, pd.Series] = {}
    for tk in tickers:
        t = norm_ticker(tk)
        if not t:
            continue
        try:
            raw = stock.get_market_ohlcv_by_date(
                start.replace("-", ""), end.replace("-", ""), t
            )
        except Exception:  # noqa: BLE001
            continue
        if raw is None or getattr(raw, "empty", True):
            continue
        close = raw["종가"] if "종가" in raw.columns else raw.iloc[:, 3]
        s = pd.to_numeric(close, errors="coerce")
        s.index = pd.to_datetime(s.index)
        cols[t] = s
    if not cols:
        return pd.DataFrame()
    return pd.DataFrame(cols).sort_index()


def build_price_panel(
    root: Path,
    tickers: Sequence[str],
    *,
    lookback_calendar_days: int = 1800,
    ensure_fetch: bool = True,
    injected: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if injected is not None and not injected.empty:
        return injected.sort_index()
    panel = _read_local_panel(root, tickers)
    end = datetime.now().strftime("%Y%m%d")
    start_dt = datetime.now() - timedelta(days=int(lookback_calendar_days))
    start = start_dt.strftime("%Y%m%d")
    missing = [norm_ticker(t) for t in tickers if norm_ticker(t) not in panel.columns]
    if ensure_fetch and (panel.empty or missing):
        fetched = _fetch_pykrx_panel(
            list(dict.fromkeys([*tickers, *missing])),
            start=start,
            end=end,
        )
        if not fetched.empty:
            panel = fetched if panel.empty else panel.combine_first(fetched)
            cache = Path(root) / "data" / "local" / "household_alloc_prices.csv"
            cache.parent.mkdir(parents=True, exist_ok=True)
            long = (
                panel.reset_index()
                .melt(id_vars=panel.index.name or "index", var_name="ticker", value_name="close")
            )
            # normalize date col
            dcol = long.columns[0]
            long = long.rename(columns={dcol: "date"})
            long = long.dropna(subset=["close"])
            long["date"] = pd.to_datetime(long["date"]).dt.strftime("%Y-%m-%d")
            long["ticker"] = long["ticker"].map(norm_ticker)
            try:
                long.to_csv(cache, index=False, encoding="utf-8")
            except OSError:
                pass
    return panel.sort_index().dropna(how="all")


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min())


def _cagr(equity: pd.Series) -> float | None:
    if len(equity) < 2:
        return None
    start = float(equity.iloc[0])
    end = float(equity.iloc[-1])
    if start <= 0 or end <= 0:
        return None
    days = (equity.index[-1] - equity.index[0]).days
    if days < 30:
        return None
    years = days / 365.25
    return float((end / start) ** (1.0 / years) - 1.0)


def _apply_cost(w_old: Mapping[str, float], w_new: Mapping[str, float], cost_bps: float) -> float:
    """One-way turnover cost as fraction of NAV."""
    keys = set(w_old) | set(w_new)
    turnover = 0.5 * sum(abs(float(w_new.get(k, 0)) - float(w_old.get(k, 0))) for k in keys)
    return turnover * (float(cost_bps) / 10000.0)


def _run_static(
    panel: pd.DataFrame,
    weights: Mapping[str, float],
    *,
    cost_bps: float,
    annual: bool = True,
) -> tuple[pd.Series, str]:
    cols = [c for c in weights if c in panel.columns]
    if not cols:
        return pd.Series(dtype=float), "no_price_columns"
    sub = panel[cols].dropna(how="any")
    if len(sub) < 60:
        return pd.Series(dtype=float), "insufficient_overlap"
    w_target = {c: float(weights[c]) for c in cols}
    s = sum(w_target.values())
    w_target = {k: v / s for k, v in w_target.items()}
    rets = sub.pct_change().fillna(0.0)
    equity = 1.0
    curve: list[tuple[pd.Timestamp, float]] = []
    w_cur = dict(w_target)
    last_year: int | None = None
    last_month: tuple[int, int] | None = None
    for i, (dt, row) in enumerate(rets.iterrows()):
        if i == 0:
            curve.append((dt, equity))
            last_year = int(dt.year)
            last_month = (int(dt.year), int(dt.month))
            continue
        day_ret = sum(float(w_cur.get(c, 0.0)) * float(row[c]) for c in cols)
        equity *= 1.0 + day_ret
        do_rebal = False
        if annual:
            if int(dt.year) != last_year and int(dt.month) == 1:
                do_rebal = True
                last_year = int(dt.year)
        else:
            ym = (int(dt.year), int(dt.month))
            if ym != last_month:
                do_rebal = True
                last_month = ym
        if do_rebal:
            cost = _apply_cost(w_cur, w_target, cost_bps)
            equity *= 1.0 - cost
            w_cur = dict(w_target)
        # drift weights
        levels = {c: float(w_cur.get(c, 0.0)) * (1.0 + float(row[c])) for c in cols}
        tot = sum(levels.values())
        if tot > 0:
            w_cur = {c: levels[c] / tot for c in cols}
        curve.append((dt, equity))
    ser = pd.Series({d: v for d, v in curve}).sort_index()
    return ser, ""


def _mom_ret(panel: pd.DataFrame, ticker: str, as_of: pd.Timestamp, months: int) -> float | None:
    if ticker not in panel.columns:
        return None
    s = panel[ticker].dropna()
    if s.empty or as_of not in s.index:
        # nearest prior
        prior = s.index[s.index <= as_of]
        if len(prior) == 0:
            return None
        as_of = prior[-1]
    end_px = float(s.loc[as_of])
    start_cut = as_of - pd.DateOffset(months=int(months))
    prior = s.index[s.index <= start_cut]
    if len(prior) == 0:
        return None
    start_px = float(s.loc[prior[-1]])
    if start_px <= 0:
        return None
    return end_px / start_px - 1.0


def _run_dual_momentum(
    panel: pd.DataFrame,
    st: Mapping[str, Any],
    *,
    cost_bps: float,
) -> tuple[pd.Series, str]:
    offs = [
        norm_ticker(x.get("ticker"))
        for x in (st.get("offensive") or [])
        if isinstance(x, dict)
    ]
    offs = [t for t in offs if t]
    cash = norm_ticker(st.get("cash_ticker"))
    safe = norm_ticker(st.get("safe_ticker"))
    months = int(st.get("lookback_months") or 12)
    need = [t for t in [*offs, cash, safe] if t]
    cols = [c for c in need if c in panel.columns]
    if len(cols) < 3:
        return pd.Series(dtype=float), "dual_missing_prices"
    sub = panel[cols].dropna(how="any")
    if len(sub) < 252:
        return pd.Series(dtype=float), "dual_insufficient_history"
    rets = sub.pct_change().fillna(0.0)
    equity = 1.0
    curve: list[tuple[pd.Timestamp, float]] = []
    hold = safe or cash
    w_cur = {hold: 1.0}
    last_month: tuple[int, int] | None = None
    for i, (dt, row) in enumerate(rets.iterrows()):
        ym = (int(dt.year), int(dt.month))
        if last_month is None:
            last_month = ym
        elif ym != last_month:
            last_month = ym
            # GEM 정석 근사: 상대 승자 → 절대(승자 vs 현금)
            # 공격축·현금 중 하나라도 12M 없으면 안전(한쪽만으로 승자 단정 금지)
            cash_m = _mom_ret(sub, cash, dt, months) if cash else None
            mom = {o: _mom_ret(sub, o, dt, months) for o in offs}
            if cash_m is None or any(r is None for r in mom.values()):
                new_hold = safe or cash
            else:
                best = max(offs, key=lambda o: float(mom[o]))  # type: ignore[arg-type]
                best_r = float(mom[best])  # type: ignore[index]
                if best_r > cash_m:
                    new_hold = best
                else:
                    new_hold = safe or cash

            new_w = {new_hold: 1.0}
            cost = _apply_cost(w_cur, new_w, cost_bps)
            equity *= 1.0 - cost
            w_cur = new_w
            hold = new_hold
        day_ret = float(row.get(hold, 0.0) or 0.0)
        if i > 0:
            equity *= 1.0 + day_ret
        curve.append((dt, equity))
    return pd.Series({d: v for d, v in curve}).sort_index(), ""


def build_strategy_curves(
    root: Path,
    *,
    ensure_fetch: bool = True,
    injected_panel: pd.DataFrame | None = None,
) -> tuple[dict[str, pd.Series], dict[str, str], Mapping[str, Any] | None]:
    """전략별 NAV 곡선 · 실패 사유 · recipes(없으면 None). Review-only."""
    root = Path(root)
    try:
        raw = load_recipes(root)
    except (OSError, ValueError, yaml.YAMLError):
        return {}, {"_": "recipes_load_fail"}, None
    verrs = validate_recipes(raw)
    if verrs:
        return {}, {"_": "; ".join(verrs[:3])}, raw
    cost = float(raw.get("cost_bps_one_way") or 15)
    lookback = int(raw.get("lookback_calendar_days") or 1800)
    tickers = collect_tickers(raw)
    panel = build_price_panel(
        root,
        tickers,
        lookback_calendar_days=lookback,
        ensure_fetch=ensure_fetch,
        injected=injected_panel,
    )
    curves: dict[str, pd.Series] = {}
    reasons: dict[str, str] = {}
    for st in raw.get("strategies") or []:
        if not isinstance(st, dict):
            continue
        sid = str(st.get("id") or "")
        kind = str(st.get("kind") or "")
        if kind == "static":
            w = _merge_static_weights(list(st.get("sleeves") or []))
            annual = str(st.get("rebalance") or "annual_jan").startswith("annual")
            curve, reason = _run_static(panel, w, cost_bps=cost, annual=annual)
        else:
            curve, reason = _run_dual_momentum(panel, st, cost_bps=cost)
        if curve.empty or reason:
            reasons[sid] = reason or "empty_curve"
        else:
            curves[sid] = curve
    return curves, reasons, raw


def run_household_alloc_lab(
    root: Path,
    *,
    ensure_fetch: bool = True,
    injected_panel: pd.DataFrame | None = None,
) -> HouseholdAllocLabReport:
    """Run all recipes · never writes target."""
    root = Path(root)
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    curves, reasons, raw = build_strategy_curves(
        root, ensure_fetch=ensure_fetch, injected_panel=injected_panel
    )
    if raw is None:
        return HouseholdAllocLabReport(
            ok=False,
            as_of=as_of,
            writes_target=False,
            caveats=list(_CAVEATS),
            strategies=[
                AllocStrategyResult(
                    id="_",
                    name_ko="load",
                    kind="error",
                    source="",
                    ok=False,
                    reason=str(reasons.get("_") or "recipes_load_fail")[:200],
                )
            ],
        )
    if "_" in reasons and not curves:
        return HouseholdAllocLabReport(
            ok=False,
            as_of=as_of,
            writes_target=False,
            caveats=list(_CAVEATS) + [reasons["_"]],
            notes_ko=str(raw.get("notes_ko") or ""),
        )
    cost = float(raw.get("cost_bps_one_way") or 15)
    results: list[AllocStrategyResult] = []
    for st in raw.get("strategies") or []:
        if not isinstance(st, dict):
            continue
        sid = str(st.get("id") or "")
        name = str(st.get("name_ko") or sid)
        kind = str(st.get("kind") or "")
        source = str(st.get("source") or "")
        if kind == "static":
            tks = list(_merge_static_weights(list(st.get("sleeves") or [])).keys())
        else:
            tks = collect_tickers({"strategies": [st]})
        curve = curves.get(sid)
        if curve is None or curve.empty:
            results.append(
                AllocStrategyResult(
                    id=sid,
                    name_ko=name,
                    kind=kind,
                    source=source,
                    ok=False,
                    reason=reasons.get(sid) or "empty_curve",
                    tickers=tks,
                )
            )
            continue
        results.append(
            AllocStrategyResult(
                id=sid,
                name_ko=name,
                kind=kind,
                source=source,
                ok=True,
                cagr=_cagr(curve),
                max_drawdown=_max_drawdown(curve),
                total_ret=float(curve.iloc[-1] / curve.iloc[0] - 1.0),
                n_days=int(len(curve)),
                start=str(curve.index[0].date()),
                end=str(curve.index[-1].date()),
                tickers=tks,
            )
        )
    ok_n = sum(1 for r in results if r.ok)
    return HouseholdAllocLabReport(
        ok=ok_n > 0,
        as_of=as_of,
        writes_target=False,
        cost_bps_one_way=cost,
        caveats=list(_CAVEATS),
        strategies=results,
        notes_ko=str(raw.get("notes_ko") or "").strip(),
    )


def save_report(root: Path, report: HouseholdAllocLabReport) -> Path:
    path = report_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ok": report.ok,
        "as_of": report.as_of,
        "review_only": True,
        "writes_target": False,
        "cost_bps_one_way": report.cost_bps_one_way,
        "caveats": report.caveats,
        "notes_ko": report.notes_ko,
        "strategies": [asdict(s) for s in report.strategies],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
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


def household_alloc_table_html(report: HouseholdAllocLabReport | Mapping[str, Any]) -> str:
    if isinstance(report, HouseholdAllocLabReport):
        rows = report.strategies
        caveats = report.caveats
        as_of = report.as_of
    else:
        rows_raw = list(report.get("strategies") or [])
        rows = rows_raw
        caveats = list(report.get("caveats") or [])
        as_of = str(report.get("as_of") or "")
    body = []
    for s in rows:
        if isinstance(s, AllocStrategyResult):
            d = asdict(s)
        else:
            d = dict(s)
        if d.get("ok"):
            cagr = d.get("cagr")
            mdd = d.get("max_drawdown")
            cagr_s = "—" if cagr is None else f"{100.0 * float(cagr):+.1f}%"
            mdd_s = "—" if mdd is None else f"{100.0 * float(mdd):.1f}%"
            status = f"{cagr_s} / {mdd_s}"
        else:
            status = str(d.get("reason") or "실패")[:40]
        body.append(
            "<tr>"
            f"<td>{_esc(d.get('name_ko'))}</td>"
            f"<td>{_esc(d.get('kind'))}</td>"
            f"<td>{status}</td>"
            f"<td class='pf-env-muted'>{_esc(str(d.get('source') or '')[:48])}</td>"
            "</tr>"
        )
    tip = " · ".join(_esc(c) for c in caveats[:4])
    return (
        '<div class="pf-hh-lab" role="region" aria-label="가계 본체 Lab">'
        '<div class="pf-hh-k">가계 본체 Lab · 정적·동적 비교 (Review-only)</div>'
        f'<div class="pf-env-muted">as_of { _esc(as_of) } · CAGR / MDD · Soft·target 불변</div>'
        "<table class='pf-hh-lab-table'><thead><tr>"
        "<th>전략</th><th>종류</th><th>CAGR / MDD</th><th>출처</th>"
        "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
        f'<div class="pf-hh-tip">{tip}</div>'
        "</div>"
    )


def _esc(v: Any) -> str:
    from html import escape

    return escape(str(v or ""))


__all__ = [
    "HouseholdAllocLabReport",
    "AllocStrategyResult",
    "build_strategy_curves",
    "collect_tickers",
    "household_alloc_table_html",
    "load_recipes",
    "load_report",
    "recipes_path",
    "report_path",
    "run_household_alloc_lab",
    "save_report",
    "validate_recipes",
    "build_price_panel",
]
