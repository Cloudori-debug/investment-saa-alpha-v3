"""Soft ↔ 행동주의 이원화 효용 검증 (Review-only).

현재 Soft Lab top · 행동주의 picks의 과거 가격으로
Soft-only / 행동주의-only / 50/50 / 실배치 / (금지)합산EW 를 비교한다.

불변: target · QVM · 자동주문 없음 · 합산 주문 권고 아님.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from alpha_system.proposal_chart import norm_ticker
from alpha_system.shadow.koizumi_kr_hakedaka_scenario import (
    BasketName,
    load_activist_basket,
    load_soft_basket,
)
from alpha_system.shadow.proposal_price_replay import proposal_replay_prices_path

WRITES_TARGET = False
REVIEW_ONLY = True
OUT_REL = Path("data") / "local" / "dual_sleeve_utility_check.json"


@dataclass
class UtilityBoard:
    as_of: str
    market: str
    soft_tickers: list[str]
    activist_tickers: list[str]
    overlap: list[str]
    missing_prices: list[str]
    window: dict[str, Any]
    sleeves: dict[str, Any]
    portfolios: dict[str, Any]
    verdict: dict[str, Any]
    review_only: bool = REVIEW_ONLY
    writes_target: bool = WRITES_TARGET
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_px(root: Path, tickers: Sequence[str]) -> pd.DataFrame:
    path = proposal_replay_prices_path(Path(root))
    if not path.is_file():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype={"ticker": str})
    df["ticker"] = df["ticker"].map(lambda x: norm_ticker(x) or "")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    want = {norm_ticker(t) for t in tickers if norm_ticker(t)}
    df = df[df["ticker"].isin(want) & df["close"].notna() & df["date"].notna()]
    return df.sort_values(["date", "ticker"])


def _wide_returns(px: pd.DataFrame, tickers: Sequence[str]) -> pd.DataFrame:
    """Date × ticker daily simple returns (aligned inner)."""
    tks = [norm_ticker(t) for t in tickers if norm_ticker(t)]
    if not tks or px.empty:
        return pd.DataFrame()
    wide = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last")
    wide = wide.reindex(columns=[t for t in tks if t in wide.columns]).dropna(how="any")
    if wide.shape[0] < 20 or wide.shape[1] == 0:
        return pd.DataFrame()
    return wide.pct_change().dropna(how="any")


def _kpi(rets: pd.Series) -> dict[str, float]:
    if rets is None or len(rets) < 5:
        return {
            "n_days": 0,
            "total_ret": float("nan"),
            "ann_ret": float("nan"),
            "ann_vol": float("nan"),
            "sharpe": float("nan"),
            "max_drawdown": float("nan"),
        }
    r = rets.astype(float)
    nav = (1.0 + r).cumprod()
    peak = nav.cummax()
    dd = (nav / peak - 1.0).min()
    mu = float(r.mean())
    sig = float(r.std(ddof=0))
    ann_ret = float((1.0 + mu) ** 252 - 1.0) if mu > -1 else float("nan")
    ann_vol = float(sig * np.sqrt(252)) if sig == sig else float("nan")
    sharpe = float(ann_ret / ann_vol) if ann_vol and ann_vol > 1e-12 else float("nan")
    return {
        "n_days": int(len(r)),
        "total_ret": round(float(nav.iloc[-1] - 1.0), 4),
        "ann_ret": round(ann_ret, 4),
        "ann_vol": round(ann_vol, 4),
        "sharpe": round(sharpe, 4) if sharpe == sharpe else float("nan"),
        "max_drawdown": round(float(dd), 4),
    }


def _ew_series(ret_wide: pd.DataFrame, tickers: Sequence[str]) -> pd.Series:
    cols = [t for t in tickers if t in ret_wide.columns]
    if not cols:
        return pd.Series(dtype=float)
    return ret_wide[cols].mean(axis=1)


def _weighted_series(
    ret_wide: pd.DataFrame, weights: dict[str, float]
) -> pd.Series:
    cols = [t for t, w in weights.items() if t in ret_wide.columns and w > 0]
    if not cols:
        return pd.Series(dtype=float)
    w = np.array([weights[t] for t in cols], dtype=float)
    w = w / w.sum()
    return (ret_wide[cols] * w).sum(axis=1)


def build_utility_board(
    root: Path | None = None,
    *,
    market: str = "KOSPI",
) -> UtilityBoard:
    root = Path(root or ".")
    mkt = str(market or "KOSPI").upper()
    soft_names = load_soft_basket(root, market=mkt)
    soft_tks = [n.ticker for n in soft_names]
    act_names = load_activist_basket(root, market=mkt, soft_tickers=soft_tks)
    act_tks = [n.ticker for n in act_names]
    overlap = sorted(set(soft_tks) & set(act_tks))

    all_tks = soft_tks + act_tks
    px = _load_px(root, all_tks)
    have = set(px["ticker"].unique()) if not px.empty else set()
    missing = sorted({t for t in all_tks if t not in have})

    soft_ok = [t for t in soft_tks if t in have]
    act_ok = [t for t in act_tks if t in have]
    ret_wide = _wide_returns(px, soft_ok + act_ok)

    notes: list[str] = []
    if missing:
        notes.append(f"가격 결측 제외: {', '.join(missing)}")
    if not soft_ok:
        notes.append("Soft 가격 없음")
    if not act_ok:
        notes.append("행동주의 가격 없음")

    soft_r = _ew_series(ret_wide, soft_ok)
    act_r = _ew_series(ret_wide, act_ok)

    # align sleeves for corr / blend
    aligned = pd.concat({"soft": soft_r, "act": act_r}, axis=1).dropna()
    corr = (
        float(aligned["soft"].corr(aligned["act"]))
        if len(aligned) >= 20
        else float("nan")
    )

    soft_w = {n.ticker: float(n.of_mid_soft_pct) for n in soft_names if n.ticker in soft_ok}
    act_w = {n.ticker: float(n.of_mid_soft_pct) for n in act_names if n.ticker in act_ok}
    # normalize within available capital (of_mid sum may be <100)
    deployed = {**soft_w, **act_w}
    # 50/50 sleeve: half capital on soft EW, half on act EW (cash if empty)
    if len(aligned):
        blend_5050 = 0.5 * aligned["soft"] + 0.5 * (
            aligned["act"] if act_ok else 0.0
        )
        if not soft_ok:
            blend_5050 = 0.5 * aligned["act"]
    else:
        blend_5050 = pd.Series(dtype=float)

    # illegal merge: one EW of all names (what dualization forbids as single score basket)
    merge_r = _ew_series(ret_wide, soft_ok + act_ok)

    # deployed: weight by of_mid, residual cash 0
    if deployed and len(ret_wide):
        # scale weights to sum of of_mid/100; cash = 1 - sum
        total_pct = sum(deployed.values())
        wmap = {t: v / 100.0 for t, v in deployed.items()}
        dep_r = _weighted_series(ret_wide, wmap)
        # cash dilutes: already using absolute of_mid/100 weights not renormalized to 1
        # so return is soft_w*rs + act_w*ra + cash*0 — need custom
        if soft_ok and act_ok and len(aligned):
            sw = sum(soft_w.values()) / 100.0
            aw = sum(act_w.values()) / 100.0
            dep_r = sw * aligned["soft"] + aw * aligned["act"]
        elif soft_ok and len(soft_r):
            sw = sum(soft_w.values()) / 100.0
            dep_r = soft_r * sw
        elif act_ok and len(act_r):
            aw = sum(act_w.values()) / 100.0
            dep_r = act_r * aw
        else:
            dep_r = pd.Series(dtype=float)
    else:
        dep_r = pd.Series(dtype=float)
        total_pct = 0.0

    portfolios = {
        "soft_only_ew": _kpi(soft_r),
        "activist_only_ew": _kpi(act_r),
        "dual_50_50": _kpi(blend_5050),
        "dual_deployed": _kpi(dep_r),
        "merged_ew_forbidden": _kpi(merge_r),
    }

    soft_kpi = portfolios["soft_only_ew"]
    dual_kpi = portfolios["dual_50_50"]
    merge_kpi = portfolios["merged_ew_forbidden"]

    # Verdict heuristics (not Go-live)
    diversifies = bool(corr == corr and corr < 0.70)
    overlap_ok = len(overlap) == 0
    dual_mdd_better = (
        soft_kpi.get("max_drawdown") == soft_kpi.get("max_drawdown")
        and dual_kpi.get("max_drawdown") == dual_kpi.get("max_drawdown")
        and dual_kpi["max_drawdown"] > soft_kpi["max_drawdown"]  # less negative
        if soft_kpi["n_days"] and dual_kpi["n_days"]
        else False
    )
    # dual vs soft: higher sharpe or better MDD counts as utility signal
    dual_sharpe_better = (
        soft_kpi["n_days"] > 0
        and dual_kpi["n_days"] > 0
        and dual_kpi["sharpe"] == dual_kpi["sharpe"]
        and soft_kpi["sharpe"] == soft_kpi["sharpe"]
        and dual_kpi["sharpe"] > soft_kpi["sharpe"]
    )

    if not act_ok:
        status = "incomplete"
        reason = "행동주의 가격/종목 부족 · 이원 효용 미확정"
    elif not soft_ok:
        status = "incomplete"
        reason = "Soft 가격 부족 · 이원 효용 미확정"
    elif overlap_ok and diversifies and (dual_mdd_better or dual_sharpe_better):
        status = "supports_dual"
        reason = "겹침 없음 · 슬리브 상관 낮음·중간 · 50/50이 Soft-only 대비 위험조정 개선 신호"
    elif overlap_ok and diversifies:
        status = "neutral_dual"
        reason = (
            "겹침 없음 · 상관으로 분산 여지 있음 · "
            "다만 50/50이 Soft-only를 위험조정으로 이기진 않음(표본·시드)"
        )
    elif not overlap_ok:
        status = "design_breach"
        reason = "Soft∩행동주의 겹침 · 이원 설계 위반"
    else:
        status = "weak_diversify"
        reason = "겹침은 없으나 슬리브 상관이 높아 분산 효용 약함"

    # merged vs dual: if merged much better, temptation to merge — still forbid by charter
    merge_tempt = (
        merge_kpi["n_days"] > 0
        and dual_kpi["n_days"] > 0
        and merge_kpi["sharpe"] == merge_kpi["sharpe"]
        and dual_kpi["sharpe"] == dual_kpi["sharpe"]
        and merge_kpi["sharpe"] > dual_kpi["sharpe"] + 0.15
    )
    if merge_tempt:
        notes.append(
            "합산EW 샤프가 50/50보다 나을 수 있으나 Soft 점수 합산·이중배팅 금지는 유지"
        )

    window = {
        "start": str(ret_wide.index.min().date()) if len(ret_wide) else None,
        "end": str(ret_wide.index.max().date()) if len(ret_wide) else None,
        "n_days": int(len(ret_wide)),
        "corr_soft_activist": round(corr, 4) if corr == corr else None,
        "deployed_soft_w": round(sum(soft_w.values()) / 100.0, 4),
        "deployed_activist_w": round(sum(act_w.values()) / 100.0, 4),
        "deployed_cash_w": round(
            max(0.0, 1.0 - sum(soft_w.values()) / 100.0 - sum(act_w.values()) / 100.0),
            4,
        ),
    }

    sleeves = {
        "soft": [{"ticker": n.ticker, "name": n.name, "of_mid": n.of_mid_soft_pct} for n in soft_names],
        "activist": [
            {"ticker": n.ticker, "name": n.name, "of_mid": n.of_mid_soft_pct} for n in act_names
        ],
    }

    verdict = {
        "status": status,
        "reason_ko": reason,
        "overlap_ok": overlap_ok,
        "diversifies_corr_lt_0_7": diversifies,
        "dual_mdd_better_than_soft": dual_mdd_better,
        "dual_sharpe_better_than_soft": dual_sharpe_better,
        "merge_temptation": bool(merge_tempt),
        "charter_keep_dual": True,
        "writes_target": False,
    }

    return UtilityBoard(
        as_of=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        market=mkt,
        soft_tickers=soft_tks,
        activist_tickers=act_tks,
        overlap=overlap,
        missing_prices=missing,
        window=window,
        sleeves=sleeves,
        portfolios=portfolios,
        verdict=verdict,
        notes=notes,
    )


def persist_board(board: UtilityBoard, root: Path | None = None) -> Path:
    root = Path(root or ".")
    path = root / OUT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(board.to_dict(), ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return path


__all__ = [
    "OUT_REL",
    "UtilityBoard",
    "WRITES_TARGET",
    "build_utility_board",
    "persist_board",
]
