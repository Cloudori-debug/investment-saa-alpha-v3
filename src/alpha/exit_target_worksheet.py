"""kr_alpha exit-target worksheet — read-only current observations for human fill-in.

Does NOT write kr_alpha_exit_targets.yaml.
`suggested_*` columns are a **reproducible policy draft** (role+ROE 2-factor) —
not calibrated / not “correct” targets. Never auto-copy into `target_*` or yaml.
See docs/KR_ALPHA_EXIT_TARGET_WORKSHEET_SPEC.md,
docs/EXIT_TARGET_SUGGESTION_RULE_SPEC.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.alpha.take_profit_thesis import assess_take_profit, load_exit_targets
from src.csv_utils import write_dataframe_csv

# Arbitrary policy constants for reproducible suggestions — not validated alphas.
PBR_ROLE_MULTIPLIER: dict[str, float] = {
    "quality_dividend": 1.2,
    "quality_defensive": 1.2,
    "shareholder_return": 1.3,
    "dividend_value": 1.3,
    "value_rerating": 1.6,
}
DEFAULT_ROE_THRESHOLD = 13.0
DEFAULT_ROE_BUFFER = 2.5
SUGGEST_DEFERRED = "제안 안 함"

WORKSHEET_COLUMNS = [
    "ticker",
    "name",
    "목표상태",
    "sector",
    "role",
    "current_weight_pct",
    "target_weight_pct",
    "roe",
    "pbr",
    "dividend_yield",
    "payout_ratio",
    "valuation_score",
    "momentum_score",
    "recent_buyback_disclosure",
    "suggested_roe_min",
    "suggested_pbr_max",
    "target_roe_min",
    "target_pbr_max",
    "target_payout_min",
    "target_buyback_done",
]

STATUS_MISSING = "⚠️ 목표 미설정"
STATUS_SET = "✅ 목표 설정됨"


def exit_target_status_label(*, has_existing_target: bool) -> str:
    """Display-only marker for take-profit target yaml presence."""
    return STATUS_SET if has_existing_target else STATUS_MISSING


def _to_float(val: Any) -> float | None:
    if val is None or val == "" or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def suggest_exit_targets(
    role: Any,
    roe: Any,
    pbr: Any,
    *,
    roe_threshold: float = DEFAULT_ROE_THRESHOLD,
    roe_buffer: float = DEFAULT_ROE_BUFFER,
) -> dict[str, Any]:
    """Role+ROE two-factor draft suggestions (EXIT_TARGET_SUGGESTION_RULE_SPEC).

    Reproducibility policy only — multipliers/buffers are unverified. No yaml write.
    Unknown / out-of-table roles → both suggestions deferred (no silent fallback).
    """
    role_n = str(role or "").strip()
    mult = PBR_ROLE_MULTIPLIER.get(role_n)
    if mult is None:
        return {
            "suggested_roe_min": SUGGEST_DEFERRED,
            "suggested_pbr_max": SUGGEST_DEFERRED,
            "fund_included": False,
            "pbr_suggested": False,
        }

    pbr_f = _to_float(pbr)
    suggested_pbr = round(pbr_f * mult, 2) if pbr_f is not None else ""

    if role_n == "quality_dividend":
        fund_included = False
    elif role_n == "value_rerating":
        fund_included = True
    else:
        roe_f = _to_float(roe)
        fund_included = roe_f is not None and roe_f < float(roe_threshold)

    if fund_included:
        roe_f = _to_float(roe)
        suggested_roe = round(roe_f + float(roe_buffer), 1) if roe_f is not None else ""
    else:
        suggested_roe = ""

    return {
        "suggested_roe_min": suggested_roe,
        "suggested_pbr_max": suggested_pbr,
        "fund_included": fund_included,
        "pbr_suggested": suggested_pbr != "",
    }


def _norm_ticker(val: Any) -> str:
    s = str(val or "").strip()
    if s.isdigit():
        return s.zfill(6)
    return s


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _latest_fundamentals(fund_df: pd.DataFrame) -> pd.DataFrame:
    if fund_df.empty or "ticker" not in fund_df.columns:
        return pd.DataFrame()
    df = fund_df.copy()
    df["ticker"] = df["ticker"].map(_norm_ticker)
    sort_cols = [c for c in ("usable_from_date", "report_date", "period_end") if c in df.columns]
    if sort_cols:
        for c in sort_cols:
            df[c] = pd.to_datetime(df[c], errors="coerce")
        df = df.sort_values(sort_cols).groupby("ticker", as_index=False).tail(1)
    else:
        df = df.drop_duplicates(subset=["ticker"], keep="last")
    return df


def _score_lookup(output_dir: Path) -> dict[str, dict[str, Any]]:
    """Prefer scored universe, then shortlist diagnostics, then candidates."""
    out: dict[str, dict[str, Any]] = {}
    for name, v_col, m_col in (
        ("alpha_scored_universe.csv", "valuation_score", "momentum_score"),
        ("alpha_shortlist_diagnostics.csv", "v_score", "m_score"),
        ("alpha_candidates.csv", "valuation_score", "momentum_score"),
        ("alpha_signal_board.csv", None, None),
    ):
        df = _read_csv(output_dir / name)
        if df.empty or "ticker" not in df.columns:
            continue
        for _, row in df.iterrows():
            t = _norm_ticker(row.get("ticker"))
            if not t or t in out:
                continue
            entry: dict[str, Any] = {}
            if v_col and v_col in df.columns:
                entry["valuation_score"] = row.get(v_col)
            if m_col and m_col in df.columns:
                entry["momentum_score"] = row.get(m_col)
            if "total_score" in df.columns and "total_score" not in entry:
                entry["total_score"] = row.get("total_score")
            out[t] = entry
        if out:
            break
    return out


def _buyback_lookup(output_dir: Path) -> dict[str, str]:
    """Map ticker → disclosure note from existing DART/treasury scan artifacts only."""
    notes: dict[str, list[str]] = {}

    def _add(ticker: str, note: str) -> None:
        t = _norm_ticker(ticker)
        if not t or not note:
            return
        notes.setdefault(t, [])
        if note not in notes[t]:
            notes[t].append(note)

    dart = _read_csv(output_dir / "hakedaka_dart_events.csv")
    if not dart.empty and "ticker" in dart.columns:
        et = dart.get("event_types", pd.Series(dtype=str)).astype(str)
        mask = et.str.contains("treasury_cancel|treasury_acquire", case=False, na=False)
        for _, row in dart.loc[mask].iterrows():
            etypes = str(row.get("event_types") or "")
            date = str(row.get("event_date") or "")
            title = str(row.get("report_title") or "")[:40]
            _add(row.get("ticker"), f"dart:{etypes}@{date} {title}".strip())

    treas = _read_csv(output_dir / "hakedaka_treasury_events.csv")
    if not treas.empty and "ticker" in treas.columns:
        et = treas.get("event_type", pd.Series(dtype=str)).astype(str)
        mask = et.str.contains("treasury_cancel|treasury_acquire", case=False, na=False)
        for _, row in treas.loc[mask].iterrows():
            date = str(row.get("event_date") or "")
            etype = str(row.get("event_type") or "")
            _add(row.get("ticker"), f"treasury:{etype}@{date}")

    ver = _read_csv(output_dir / "hakedaka_dart_verification.csv")
    if not ver.empty and "ticker" in ver.columns and "cancel_disclosure" in ver.columns:
        for _, row in ver.iterrows():
            if bool(row.get("cancel_disclosure")):
                _add(row.get("ticker"), f"verify:cancel_disclosure@{row.get('dart_latest_date') or ''}")

    return {t: "; ".join(v) if v else "" for t, v in notes.items()}


def _payout_lookup(data_dir: Path) -> dict[str, Any]:
    hk = _read_csv(data_dir / "hakedaka_fundamentals.csv")
    if hk.empty or "ticker" not in hk.columns or "payout_ratio" not in hk.columns:
        return {}
    hk = hk.copy()
    hk["ticker"] = hk["ticker"].map(_norm_ticker)
    if "as_of" in hk.columns:
        hk["as_of"] = pd.to_datetime(hk["as_of"], errors="coerce")
        hk = hk.sort_values("as_of").groupby("ticker", as_index=False).tail(1)
    else:
        hk = hk.drop_duplicates(subset=["ticker"], keep="last")
    return {str(r["ticker"]): r.get("payout_ratio") for _, r in hk.iterrows()}


def _position_weights(data_dir: Path) -> dict[str, float]:
    pos = _read_csv(data_dir / "positions.csv")
    if pos.empty or "ticker" not in pos.columns or "current_value" not in pos.columns:
        return {}
    pos = pos.copy()
    pos["ticker"] = pos["ticker"].map(_norm_ticker)
    pos["current_value"] = pd.to_numeric(pos["current_value"], errors="coerce").fillna(0.0)
    total = float(pos["current_value"].sum())
    if total <= 0:
        return {}
    return {
        str(r["ticker"]): round(float(r["current_value"]) / total * 100.0, 2)
        for _, r in pos.iterrows()
    }


def _has_existing_target(exit_cfg: dict[str, Any], ticker: str) -> bool:
    tickers = exit_cfg.get("tickers") or {}
    raw = tickers.get(_norm_ticker(ticker)) or tickers.get(ticker) or {}
    if not isinstance(raw, dict):
        return False
    return not assess_take_profit(ticker, targets=raw).targets_missing


def _park_tickers(data_dir: Path) -> list[dict[str, Any]]:
    park = _read_csv(data_dir / "park_state.csv")
    if park.empty or "ticker" not in park.columns:
        return []
    rows = []
    for _, r in park.iterrows():
        rows.append(
            {
                "ticker": _norm_ticker(r.get("ticker")),
                "name": r.get("name") or "",
                "sector": r.get("sector") or "",
                "role": "park",
                "target_weight": 0.0,
            }
        )
    return rows


def _series_get(row: Any, key: str) -> Any:
    if row is None:
        return ""
    if isinstance(row, dict):
        val = row.get(key, "")
        return "" if val is None or (isinstance(val, float) and pd.isna(val)) else val
    if hasattr(row, "index") and key in row.index:
        val = row[key]
        return "" if val is None or (isinstance(val, float) and pd.isna(val)) else val
    return ""


def build_exit_target_worksheet(
    data_dir: Path,
    output_dir: Path,
) -> pd.DataFrame:
    """Assemble current kr_alpha observations; leave target_* columns blank."""
    target = _read_csv(data_dir / "target_portfolio.csv")
    if target.empty:
        return pd.DataFrame(columns=WORKSHEET_COLUMNS)

    target = target.copy()
    target["ticker"] = target["ticker"].map(_norm_ticker)
    kr = target[target["asset_group"].astype(str).str.lower() == "kr_alpha"].copy()

    park_rows = _park_tickers(data_dir)
    if park_rows:
        seen = set(kr["ticker"].astype(str))
        extra = [r for r in park_rows if r["ticker"] and r["ticker"] not in seen]
        if extra:
            kr = pd.concat([kr, pd.DataFrame(extra)], ignore_index=True)

    fund = _latest_fundamentals(_read_csv(data_dir / "fundamentals.csv"))
    fund_by = {str(r["ticker"]): r for _, r in fund.iterrows()} if not fund.empty else {}
    scores = _score_lookup(output_dir)
    buybacks = _buyback_lookup(output_dir)
    payouts = _payout_lookup(data_dir)
    weights = _position_weights(data_dir)
    exit_cfg = load_exit_targets(data_dir / "kr_alpha_exit_targets.yaml")

    rows: list[dict[str, Any]] = []
    for _, r in kr.iterrows():
        t = _norm_ticker(r.get("ticker"))
        f = fund_by.get(t)
        sc = scores.get(t) or {}
        tw = r.get("target_weight") if "target_weight" in r.index else ""
        if tw is None or (isinstance(tw, float) and pd.isna(tw)):
            tw = ""
        cw = weights.get(t, "")
        role = r.get("role") or ""
        roe_v = _series_get(f, "roe")
        pbr_v = _series_get(f, "pbr")
        suggestion = suggest_exit_targets(role, roe_v, pbr_v)
        rows.append(
            {
                "ticker": t,
                "name": r.get("name") or "",
                "sector": r.get("sector") or "",
                "role": role,
                "current_weight_pct": cw,
                "target_weight_pct": tw,
                "roe": roe_v,
                "pbr": pbr_v,
                "dividend_yield": _series_get(f, "dividend_yield"),
                "payout_ratio": payouts.get(t, "") if payouts.get(t) is not None and not (
                    isinstance(payouts.get(t), float) and pd.isna(payouts.get(t))
                ) else "",
                "valuation_score": sc.get("valuation_score", ""),
                "momentum_score": sc.get("momentum_score", ""),
                "recent_buyback_disclosure": buybacks.get(t, ""),
                "목표상태": exit_target_status_label(
                    has_existing_target=_has_existing_target(exit_cfg, t)
                ),
                "suggested_roe_min": suggestion["suggested_roe_min"],
                "suggested_pbr_max": suggestion["suggested_pbr_max"],
                "target_roe_min": "",
                "target_pbr_max": "",
                "target_payout_min": "",
                "target_buyback_done": "",
            }
        )

    df = pd.DataFrame(rows, columns=WORKSHEET_COLUMNS)
    if not df.empty:
        df["ticker"] = df["ticker"].map(_norm_ticker)
        if "target_weight_pct" in df.columns:
            tw_num = pd.to_numeric(df["target_weight_pct"], errors="coerce")
            df = df.assign(_tw=tw_num).sort_values("_tw", ascending=False, kind="mergesort").drop(columns=["_tw"])
    return df.reset_index(drop=True)


def write_exit_target_worksheet(
    data_dir: Path,
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    df = build_exit_target_worksheet(data_dir, output_dir)
    if not df.empty:
        df = df.copy()
        df["ticker"] = df["ticker"].map(_norm_ticker).astype(str)
    path = output_dir / "kr_alpha_exit_target_worksheet.csv"
    write_dataframe_csv(path, df, columns=WORKSHEET_COLUMNS)

    missing_n = 0
    if not df.empty and "목표상태" in df.columns:
        missing_n = int((df["목표상태"].astype(str) == STATUS_MISSING).sum())
    total_n = len(df)
    banner = ""
    if missing_n > 0:
        banner = (
            f"⚠️ {missing_n}/{total_n} 종목 목표 미설정 — "
            f"data/kr_alpha_exit_targets.yaml에서 직접 입력"
        )

    md_lines = [
        "# kr_alpha 익절 목표가 워크시트 (현재값 + 제안 참고)",
        "",
        "> `target_*` 칸은 비움 — 사람이 `data/kr_alpha_exit_targets.yaml`에 직접 기입.",
        "> `suggested_*`는 role+ROE 2요인 **재현 정책 초안**(배수·버퍼 미검증). "
        "정답이 아니며 yaml/target_*에 자동 복사하지 않음.",
        "",
    ]
    if banner:
        md_lines.extend([banner, ""])
    md_lines.extend(
        [
            f"종목 수: {total_n}",
            "",
            df.to_string(index=False) if not df.empty else "(empty)",
            "",
        ]
    )
    md_path = output_dir / "kr_alpha_exit_target_worksheet.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return path
