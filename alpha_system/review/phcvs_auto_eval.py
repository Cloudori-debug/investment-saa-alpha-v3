"""PH-CVS stage-1 auto-eval — price / liquidity / S00·S03 ceilings.

Review-only: never writes ``target_portfolio.csv``, QVM ranks, or Core scores.
Cash residual / dividend cover stay as seed snapshots (not recomputed from DART).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

MODEL_VERSION = "phcvs-auto-eval-v1"

WATCH_REL = Path("data") / "phcvs_observation_watch.json"
SNAPSHOT_REL = Path("data") / "phcvs_eval_snapshot.json"
PRICES_REL = Path("data") / "prices.csv"
DEFAULT_UNIVERSE = (
    Path(__file__).resolve().parents[1] / "config" / "phcvs_universe.yaml"
)

# Hard guards — tests assert these never appear as write targets.
FORBIDDEN_WRITE_NAMES = frozenset(
    {
        "target_portfolio.csv",
        "alpha_scores.csv",
        "kr_alpha_exit_targets.yaml",
    }
)


@dataclass(frozen=True)
class PriceRow:
    date: str
    close: float
    market_cap: float
    trading_value_20d: float


@dataclass(frozen=True)
class NameEval:
    ticker: str
    name: str
    phcvs_status: str
    screener_status: str
    reason: str
    action: str
    review_only: bool
    close: float | None
    as_of_price: str
    market_cap_eok: float | None
    adv20_eok: float | None
    s00_ceiling: float
    s03_ceiling: float
    premium_to_s00_pct: float | None
    drop_needed_to_s00_pct: float | None
    price_gate: str
    liquidity_gate: str
    cash_gate: str
    cash_residual_eok: float | None
    dividend_cover: float | None
    cash_as_of: str
    cash_stale: bool
    track_only: bool
    required_return: float
    years: int
    dps: float
    fixed_reference_price: float


def _norm_ticker(raw: object) -> str:
    text = str(raw or "").strip()
    if text.isdigit():
        return text.zfill(6)
    return text


def _f(raw: object) -> float | None:
    try:
        if raw is None or str(raw).strip() == "":
            return None
        return float(raw)
    except (TypeError, ValueError):
        return None


def load_universe(path: Path | None = None) -> dict[str, Any]:
    import yaml

    p = Path(path) if path else DEFAULT_UNIVERSE
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"invalid PH-CVS universe: {p}")
    return raw


def entry_price_ceiling(
    *,
    dps: float,
    fixed_reference_price: float,
    required_return: float,
    years: int,
    price_multipliers: Sequence[float],
    dps_multipliers: Sequence[float],
    act365_years: Sequence[float],
    buy_fee: float = 0.00015,
    sell_fee: float = 0.00015,
    sell_tax: float = 0.002,
    dividend_tax: float = 0.154,
) -> float:
    """Discounted entry ceiling (audit Pmax). Terminal = ref × last price multiplier."""
    if years < 1:
        raise ValueError("years must be >= 1")
    if len(act365_years) < years:
        raise ValueError("act365_years shorter than years")
    if len(price_multipliers) < years or len(dps_multipliers) < years:
        raise ValueError("multiplier paths shorter than years")

    div_net = 1.0 - float(dividend_tax)
    sell_keep = 1.0 - float(sell_fee) - float(sell_tax)
    r = float(required_return)
    total = 0.0
    for i in range(years):
        t = float(act365_years[i])
        dps_t = float(dps) * float(dps_multipliers[i])
        total += dps_t * div_net / ((1.0 + r) ** t)
    pt = float(fixed_reference_price) * float(price_multipliers[years - 1])
    t_end = float(act365_years[years - 1])
    total += pt * sell_keep / ((1.0 + r) ** t_end)
    return total / (1.0 + float(buy_fee))


def load_latest_prices(root: Path) -> tuple[str, dict[str, PriceRow]]:
    path = Path(root) / PRICES_REL
    if not path.is_file():
        return "", {}
    try:
        import pandas as pd

        df = pd.read_csv(path, dtype=str)
    except (OSError, ValueError):
        return "", {}
    if df.empty or "ticker" not in df.columns:
        return "", {}
    as_of = ""
    if "date" in df.columns:
        df = df.sort_values("date")
        as_of = str(df["date"].iloc[-1] or "")
        df = df.groupby("ticker", as_index=False).tail(1)
    out: dict[str, PriceRow] = {}
    for _, row in df.iterrows():
        tk = _norm_ticker(row.get("ticker"))
        close = _f(row.get("close"))
        if not tk or close is None:
            continue
        out[tk] = PriceRow(
            date=str(row.get("date") or as_of),
            close=float(close),
            market_cap=float(_f(row.get("market_cap")) or 0.0),
            trading_value_20d=float(_f(row.get("trading_value_20d")) or 0.0),
        )
    return as_of, out


def _liquidity_status(
    *,
    market_cap: float,
    adv20: float,
    min_cap: float,
    min_adv: float,
) -> tuple[str, str, str]:
    """Return (screener_status, liquidity_gate, reason_fragment)."""
    cap_ok = market_cap >= min_cap
    adv_ok = adv20 >= min_adv
    if cap_ok and adv_ok:
        return "유동성 통과급", "PASS", "시총·ADV20 하한 충족"
    if (not cap_ok) and (not adv_ok):
        return (
            "정량풀 밖",
            "FAIL",
            f"시총·ADV20 모두 하한 미달 ({min_cap/1e8:.0f}억 / {min_adv/1e8:.0f}억)",
        )
    if not adv_ok:
        return (
            "게이트 탈락",
            "FAIL",
            f"ADV20≈{adv20/1e8:.1f}억 < {min_adv/1e8:.0f}억 → low_liquidity",
        )
    return (
        "정량풀 밖",
        "FAIL",
        f"시총≈{market_cap/1e8:.0f}억 < {min_cap/1e8:.0f}억",
    )


def _premium_drop(close: float, ceiling: float) -> tuple[float, float]:
    """(premium_over_ceiling_pct, drop_needed_pct)."""
    if ceiling <= 0:
        return 0.0, 0.0
    premium = (close / ceiling - 1.0) * 100.0
    drop = (1.0 - ceiling / close) * 100.0 if close > 0 else 0.0
    return premium, drop


def _build_action(
    *,
    seed_action: str,
    price_gate: str,
    liquidity_gate: str,
    cash_gate: str,
) -> str:
    parts = [seed_action.strip()] if seed_action.strip() else []
    if liquidity_gate != "PASS":
        parts.append("유동성 미충족 · 추적 전용 · 매수 금지")
    if price_gate != "PASS":
        parts.append("가격게이트 미충족")
    elif cash_gate != "PASS":
        parts.append("가격만 진입 · 현금/권리 미재검증 · 자동 승격 없음")
    else:
        parts.append("가격·현금시드 PASS · 권리·반복성 사람 Review · 자동 편입 없음")
    # de-dupe while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return " · ".join(out)


def evaluate_name(
    item: Mapping[str, Any],
    *,
    model: Mapping[str, Any],
    liquidity: Mapping[str, Any],
    price: PriceRow | None,
    cash_as_of: str,
) -> NameEval:
    ticker = _norm_ticker(item.get("ticker"))
    name = str(item.get("name") or ticker)
    dps = float(item.get("dps") or 0.0)
    ref = float(item.get("fixed_reference_price") or 0.0)
    years = int(model.get("years") or 5)
    r = float(model.get("required_return") or 0.10)
    act = list(model.get("act365_years") or [])
    s00 = model.get("S00") or {}
    s03 = model.get("S03") or {}
    fees = dict(
        buy_fee=float(model.get("buy_fee") or 0.00015),
        sell_fee=float(model.get("sell_fee") or 0.00015),
        sell_tax=float(model.get("sell_tax") or 0.002),
        dividend_tax=float(model.get("dividend_tax") or 0.154),
    )
    s00_ceil = entry_price_ceiling(
        dps=dps,
        fixed_reference_price=ref,
        required_return=r,
        years=years,
        price_multipliers=list(s00.get("price_multipliers") or [1] * years),
        dps_multipliers=list(s00.get("dps_multipliers") or [1] * years),
        act365_years=act,
        **fees,
    )
    s03_ceil = entry_price_ceiling(
        dps=dps,
        fixed_reference_price=ref,
        required_return=r,
        years=years,
        price_multipliers=list(s03.get("price_multipliers") or [0.6] * years),
        dps_multipliers=list(s03.get("dps_multipliers") or [0.5] * years),
        act365_years=act,
        **fees,
    )

    cash = item.get("cash") or {}
    cash_gate = str(cash.get("cash_gate") or "U").upper()
    residual = _f(cash.get("residual_eok"))
    cover = _f(cash.get("dividend_cover"))

    min_cap = float(liquidity.get("min_market_cap_krw") or 5e11)
    min_adv = float(liquidity.get("min_20d_adv_krw") or 1.5e9)

    if price is None:
        screener_status = "가격 없음"
        liq_gate = "FAIL"
        liq_reason = "prices.csv에 종목 없음"
        close = None
        as_of_p = ""
        cap_eok = None
        adv_eok = None
        premium = None
        drop = None
        price_gate = "FAIL"
    else:
        close = price.close
        as_of_p = price.date
        cap_eok = price.market_cap / 1e8 if price.market_cap else None
        adv_eok = price.trading_value_20d / 1e8 if price.trading_value_20d else None
        screener_status, liq_gate, liq_reason = _liquidity_status(
            market_cap=price.market_cap,
            adv20=price.trading_value_20d,
            min_cap=min_cap,
            min_adv=min_adv,
        )
        premium, drop = _premium_drop(close, s00_ceil)
        price_gate = "PASS" if close <= s00_ceil else "FAIL"

    seed_action = str(item.get("seed_action") or "")
    action = _build_action(
        seed_action=seed_action,
        price_gate=price_gate,
        liquidity_gate=liq_gate,
        cash_gate=cash_gate,
    )
    reasons = [liq_reason]
    if close is not None and premium is not None:
        if price_gate == "PASS":
            reasons.append(f"종가 {close:,.0f} ≤ S00 {s00_ceil:,.0f}")
        else:
            reasons.append(
                f"종가 {close:,.0f} > S00 {s00_ceil:,.0f} "
                f"(할증 {premium:.1f}% · 필요하락 {drop:.1f}%)"
            )
    reasons.append(f"현금시드 {cash_gate} (잔여 {residual}억 · 자동재산출 아님)")

    track_only = liq_gate != "PASS"
    return NameEval(
        ticker=ticker,
        name=name,
        phcvs_status=str(item.get("phcvs_status") or ""),
        screener_status=screener_status,
        reason=" · ".join(reasons),
        action=action,
        review_only=True,
        close=close,
        as_of_price=as_of_p,
        market_cap_eok=round(cap_eok, 1) if cap_eok is not None else None,
        adv20_eok=round(adv_eok, 1) if adv_eok is not None else None,
        s00_ceiling=round(s00_ceil, 2),
        s03_ceiling=round(s03_ceil, 2),
        premium_to_s00_pct=round(premium, 2) if premium is not None else None,
        drop_needed_to_s00_pct=round(drop, 2) if drop is not None else None,
        price_gate=price_gate,
        liquidity_gate=liq_gate,
        cash_gate=cash_gate,
        cash_residual_eok=residual,
        dividend_cover=cover,
        cash_as_of=cash_as_of,
        cash_stale=True,
        track_only=track_only,
        required_return=r,
        years=years,
        dps=dps,
        fixed_reference_price=ref,
    )


def evaluate_phcvs(
    root: Path,
    *,
    universe_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (watch_payload, snapshot_payload). No disk writes."""
    uni = load_universe(universe_path)
    model = uni.get("model") or {}
    liquidity = uni.get("liquidity") or {}
    meta = uni.get("screener_meta") or {}
    cash_as_of = str(uni.get("cash_as_of") or "")
    as_of_prices, prices = load_latest_prices(root)

    evals: list[NameEval] = []
    for item in uni.get("names") or []:
        if not isinstance(item, dict):
            continue
        tk = _norm_ticker(item.get("ticker"))
        evals.append(
            evaluate_name(
                item,
                model=model,
                liquidity=liquidity,
                price=prices.get(tk),
                cash_as_of=cash_as_of,
            )
        )

    n_price_pass = sum(1 for e in evals if e.price_gate == "PASS")
    n_liq_pass = sum(1 for e in evals if e.liquidity_gate == "PASS")
    n_cash_pass = sum(1 for e in evals if e.cash_gate == "PASS")
    summary = (
        f"자동평가 {len(evals)}종 · 가격게이트 PASS {n_price_pass} · "
        f"유동성 PASS {n_liq_pass} · 현금시드 PASS {n_cash_pass} · "
        f"최종 제안 자동편입 0 · Review-only"
    )

    names_watch = []
    names_snap = []
    for e in evals:
        names_watch.append(
            {
                "ticker": e.ticker,
                "name": e.name,
                "phcvs_status": e.phcvs_status,
                "screener_status": e.screener_status,
                "market_cap_eok": e.market_cap_eok,
                "adv20_eok": e.adv20_eok,
                "reason": e.reason,
                "action": e.action,
                "review_only": True,
                "close": e.close,
                "s00_ceiling": e.s00_ceiling,
                "s03_ceiling": e.s03_ceiling,
                "premium_to_s00_pct": e.premium_to_s00_pct,
                "drop_needed_to_s00_pct": e.drop_needed_to_s00_pct,
                "price_gate": e.price_gate,
                "liquidity_gate": e.liquidity_gate,
                "cash_gate": e.cash_gate,
                "cash_residual_eok": e.cash_residual_eok,
                "dividend_cover": e.dividend_cover,
                "cash_as_of": e.cash_as_of,
                "cash_stale": e.cash_stale,
                "track_only": e.track_only,
            }
        )
        names_snap.append(asdict(e))

    evaluated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    watch = {
        "as_of_report": str(uni.get("as_of_report") or ""),
        "as_of_prices": as_of_prices,
        "evaluated_at": evaluated_at,
        "model_version": str(uni.get("model_version") or MODEL_VERSION),
        "source": str(uni.get("source") or ""),
        "auto_eval": True,
        "screener": {
            "market": meta.get("market", "KOSPI"),
            "score_cutoff": meta.get("score_cutoff"),
            "target_names": meta.get("target_names"),
            "liquid_preset": meta.get("liquid_preset", "standard"),
            "min_market_cap_krw": liquidity.get("min_market_cap_krw"),
            "min_20d_adv_krw": liquidity.get("min_20d_adv_krw"),
            "min_cap_eok": liquidity.get("min_cap_eok"),
            "min_adv20_eok": liquidity.get("min_adv20_eok"),
        },
        "charter": {
            "target_portfolio_written": False,
            "proposal_mode": "pure_qvm",
            "note": (
                "관찰 자동평가 · QVM 순위·target_portfolio 자동 변경 없음 · "
                "즉시매수 지시 아님 · 현금필드는 시드(자동 재산출 아님)"
            ),
        },
        "summary": summary,
        "names": names_watch,
    }
    snapshot = {
        "model_version": str(uni.get("model_version") or MODEL_VERSION),
        "evaluated_at": evaluated_at,
        "as_of_report": str(uni.get("as_of_report") or ""),
        "as_of_prices": as_of_prices,
        "cash_as_of": cash_as_of,
        "cash_stale": True,
        "required_return": float(model.get("required_return") or 0.10),
        "years": int(model.get("years") or 5),
        "charter": {
            "target_portfolio_written": False,
            "proposal_mode": "pure_qvm",
        },
        "summary": summary,
        "names": names_snap,
    }
    return watch, snapshot


def _assert_safe_write_path(path: Path) -> None:
    name = path.name.lower()
    if name in FORBIDDEN_WRITE_NAMES:
        raise RuntimeError(f"charter guard: refusing to write {path.name}")


def run_and_write(
    root: Path,
    *,
    universe_path: Path | None = None,
) -> tuple[Path, Path]:
    """Evaluate and write watch + snapshot only under data/."""
    root = Path(root)
    watch, snapshot = evaluate_phcvs(root, universe_path=universe_path)
    watch_path = root / WATCH_REL
    snap_path = root / SNAPSHOT_REL
    _assert_safe_write_path(watch_path)
    _assert_safe_write_path(snap_path)
    watch_path.parent.mkdir(parents=True, exist_ok=True)
    watch_path.write_text(
        json.dumps(watch, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    snap_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return watch_path, snap_path


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="PH-CVS Review-only auto-eval (price/liquidity/S00·S03)."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="repo root (default: cwd)",
    )
    parser.add_argument(
        "--universe",
        type=Path,
        default=None,
        help="override phcvs_universe.yaml path",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    w, s = run_and_write(args.root, universe_path=args.universe)
    print(f"wrote {w}")
    print(f"wrote {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
