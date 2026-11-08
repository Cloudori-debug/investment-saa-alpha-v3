"""듀얼모멘텀(GEM) 실운영 시그널 · Review-only.

Antonacci Dual Momentum / GEM 정석 근사 (국내상장):
1) 상대: 미국 vs EAFE(선진국 ex-US) 중 12M 승자
2) 절대: 그 승자 12M > 달러단기채 ? 아니면 미종합채
월말 점검 · 픽이 바뀔 때만 매매 · target/자동주문 없음
코스피·유로50단독·배당30은 듀얼 공격축에 넣지 않음.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alpha_system.proposal_chart import norm_ticker


@dataclass
class DualAssetRet:
    ticker: str
    name: str
    role: str
    ret_12m: float | None


@dataclass
class DualMomentumSignal:
    ok: bool
    as_of: str
    lookback_months: int = 12
    assets: list[DualAssetRet] = field(default_factory=list)
    absolute_ok: bool | None = None
    pick_ticker: str = ""
    pick_name: str = ""
    pick_role: str = ""
    reason_ko: str = ""
    checklist: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    review_only: bool = True
    writes_target: bool = False
    error: str = ""


def _load_dual_recipe(root: Path) -> dict[str, Any] | None:
    from alpha_system.shadow.household_alloc_lab import load_recipes

    raw = load_recipes(root)
    for stg in raw.get("strategies") or []:
        if isinstance(stg, dict) and str(stg.get("id")) == "dual_momentum":
            return stg
    return None


def compute_dual_momentum_signal(
    root: Path,
    *,
    ensure_fetch: bool = False,
) -> DualMomentumSignal:
    """월 운영용 현재 시그널 산출."""
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    caveats = [
        "국내상장 대리: SPY≈360750 · EAFE≈195970 · BIL≈329750 · AGG≈437080",
        "ACWI ex-US·미헤지 EAFE 부재 · 195970은 합성(H)·EAFE(EM·캐나다 제외)",
        "코스피 Soft·정적·유로50단독·배당30과 합산 집행 금지 · 배당/과세 미반영",
    ]
    stg = _load_dual_recipe(root)
    if not stg:
        return DualMomentumSignal(
            ok=False, as_of=as_of, error="dual_momentum 레시피 없음", caveats=caveats
        )
    months = int(stg.get("lookback_months") or 12)
    offs = [
        (norm_ticker(o.get("ticker")), str(o.get("name") or ""))
        for o in (stg.get("offensive") or [])
        if isinstance(o, dict)
    ]
    offs = [(t, n) for t, n in offs if t]
    cash = norm_ticker(stg.get("cash_ticker"))
    safe = norm_ticker(stg.get("safe_ticker"))
    cash_n = str(stg.get("cash_name") or cash)
    safe_n = str(stg.get("safe_name") or safe)
    if len(offs) < 2 or not cash or not safe:
        return DualMomentumSignal(
            ok=False,
            as_of=as_of,
            error="공격2·현금·안전 티커 필요",
            caveats=caveats,
        )

    from alpha_system.shadow.household_alloc_lab import (
        _mom_ret,
        build_price_panel,
    )

    tickers = [t for t, _ in offs] + [cash, safe]
    try:
        panel = build_price_panel(
            Path(root), tickers, ensure_fetch=ensure_fetch
        )
    except Exception as exc:  # noqa: BLE001
        return DualMomentumSignal(
            ok=False, as_of=as_of, error=str(exc)[:200], caveats=caveats
        )
    if panel.empty:
        return DualMomentumSignal(
            ok=False,
            as_of=as_of,
            error="가격 패널 없음 · ETF Lab 갱신 필요",
            caveats=caveats,
        )

    clean = panel.dropna(how="all")
    if clean.empty:
        return DualMomentumSignal(
            ok=False, as_of=as_of, error="유효 가격 없음", caveats=caveats
        )
    dt = clean.index.max()
    as_of_px = str(getattr(dt, "date", lambda: dt)())

    def ret(tk: str) -> float | None:
        return _mom_ret(clean, tk, dt, months)

    assets: list[DualAssetRet] = []
    for i, (tk, name) in enumerate(offs):
        role = "미국주식" if i == 0 else ("EAFE·선진ex-US" if i == 1 else "공격")
        assets.append(
            DualAssetRet(ticker=tk, name=name, role=role, ret_12m=ret(tk))
        )
    assets.append(
        DualAssetRet(ticker=cash, name=cash_n, role="현금·달러단기(BIL)", ret_12m=ret(cash))
    )
    assets.append(
        DualAssetRet(ticker=safe, name=safe_n, role="안전·미종합채(AGG)", ret_12m=ret(safe))
    )

    cash_m = ret(cash)
    # ① 상대: 공격축 전원의 12M이 있어야 함(한쪽만으로 승자 단정 금지)
    missing_off = [f"{n}({tk})" for tk, n in offs if ret(tk) is None]
    if missing_off or cash_m is None:
        return DualMomentumSignal(
            ok=False,
            as_of=as_of_px,
            assets=assets,
            lookback_months=months,
            error=(
                "12M 수익률 산출 불가 · "
                + (
                    "가격 갱신 필요: " + ", ".join(missing_off)
                    if missing_off
                    else "현금 가격 기간 부족"
                )
            ),
            caveats=caveats,
        )
    best_tk, best_n, best_r = offs[0][0], offs[0][1], ret(offs[0][0])
    for tk, name in offs[1:]:
        r = ret(tk)
        assert r is not None and best_r is not None
        if r > best_r:
            best_tk, best_n, best_r = tk, name, r

    # ② 절대: 상대 승자 vs 달러단기채
    absolute_ok = bool(best_r > cash_m)
    if not absolute_ok:
        pick_tk, pick_n, pick_role = safe, safe_n, "안전(절대모멘텀 실패)"
        reason = (
            f"상대 승자 {best_n}({best_tk}) 12M {100.0 * best_r:+.1f}% "
            f"≤ 현금 {100.0 * cash_m:+.1f}% → {safe_n}({safe}) 전량"
        )
    else:
        pick_tk, pick_n, pick_role = best_tk, best_n, "공격(상대 승자·절대 OK)"
        reason = (
            f"상대 승자 {best_n}({best_tk}) 12M {100.0 * best_r:+.1f}% "
            f"> 현금 {100.0 * cash_m:+.1f}% → 전량"
        )

    checklist = [
        f"기준일(가격) {as_of_px} · 룩백 {months}개월",
        "① 상대: 미국 vs EAFE(선진국 ex-US) 중 12M 높은 ETF",
        "② 절대: 그 승자 12M > 달러단기채 ? 예→승자 100% / 아니오→미종합채 100%",
        "③ 보유와 픽이 같으면 홀드 · 다르면 전량 교체(월 0~1회)",
        "④ 코스피 Soft·유로50단독·배당30은 듀얼 공격축 아님",
        "⑤ Soft·정적과 비중 합산 집행 금지 · target 자동 없음",
    ]
    return DualMomentumSignal(
        ok=True,
        as_of=as_of_px,
        lookback_months=months,
        assets=assets,
        absolute_ok=absolute_ok,
        pick_ticker=pick_tk or "",
        pick_name=pick_n or "",
        pick_role=pick_role,
        reason_ko=reason,
        checklist=checklist,
        caveats=caveats,
    )


def dual_signal_to_rows(sig: DualMomentumSignal) -> list[dict[str, str]]:
    rows = []
    for a in sig.assets:
        r = "—" if a.ret_12m is None else f"{100.0 * float(a.ret_12m):+.1f}%"
        mark = "◀ 픽" if a.ticker == sig.pick_ticker else ""
        rows.append(
            {
                "역할": a.role,
                "종목": a.name,
                "티커": a.ticker,
                "12M": r,
                "": mark,
            }
        )
    return rows


def dual_signal_dict(sig: DualMomentumSignal) -> dict[str, Any]:
    return asdict(sig)


SIGNAL_REL = Path("data") / "local" / "dual_momentum_signal.json"


def persist_dual_signal(root: Path, sig: DualMomentumSignal) -> Path:
    """월 운영 참고용 스냅샷 · target 불변."""
    import json

    path = Path(root) / SIGNAL_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dual_signal_dict(sig), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def compute_and_persist(
    root: Path, *, ensure_fetch: bool = False
) -> DualMomentumSignal:
    sig = compute_dual_momentum_signal(root, ensure_fetch=ensure_fetch)
    if sig.ok:
        try:
            persist_dual_signal(root, sig)
        except Exception:  # noqa: BLE001
            pass
    return sig


__all__ = [
    "DualAssetRet",
    "DualMomentumSignal",
    "SIGNAL_REL",
    "compute_and_persist",
    "compute_dual_momentum_signal",
    "dual_signal_dict",
    "dual_signal_to_rows",
    "persist_dual_signal",
]
