"""전략별 투자 후보 — Soft 제안 · ETF 슬리브 · 듀얼 현재픽 (Review-only)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from alpha_system.proposal_chart import norm_ticker
from alpha_system.ui.services.strategy_ops_catalog import STRATEGY_OP_SPECS


REPORT_REL = Path("data") / "local" / "strategy_candidates_snapshot.json"

# 포트 유니버스 기본 지도 = 추천 스택만 (Lab 정적 후보 전원 나열 금지)
OPS_STACK_IDS: tuple[str, ...] = (
    "static_book",  # 가계 본체 = compass_fit
    "dual_momentum",  # 선택 위성
    "mid_soft",  # 알파 Soft
    "short_momentum",  # 단기 위성(얇게)
)

# 가계 추천스택 합=100 (Review 지도 · 합산 집행·target 자동 없음)
# 본체 70~85 · 듀얼 0~15 · Soft 10~20 · 단기 0~5 감각의 중앙값
OPS_STACK_BUDGET_PCT: dict[str, float] = {
    "static_book": 75.0,
    "dual_momentum": 10.0,
    "mid_soft": 12.0,
    "short_momentum": 3.0,
}

# 계좌 이분 · 합산 집행 금지 · Review 지도만
# 연금·ISA = 중장기 정적(+세 효율 듀얼) · 일반 = Soft·단기
ACCOUNT_PENSION = "pension"
ACCOUNT_TAXABLE = "taxable"
ACCOUNT_LABEL_KO: dict[str, str] = {
    ACCOUNT_PENSION: "연금·ISA",
    ACCOUNT_TAXABLE: "일반",
}
STRATEGY_ACCOUNT: dict[str, str] = {
    "static_book": ACCOUNT_PENSION,
    "dual_momentum": ACCOUNT_PENSION,
    "mid_soft": ACCOUNT_TAXABLE,
    "short_momentum": ACCOUNT_TAXABLE,
}
ACCOUNT_BUDGET_PCT: dict[str, float] = {
    ACCOUNT_PENSION: float(OPS_STACK_BUDGET_PCT["static_book"])
    + float(OPS_STACK_BUDGET_PCT["dual_momentum"]),
    ACCOUNT_TAXABLE: float(OPS_STACK_BUDGET_PCT["mid_soft"])
    + float(OPS_STACK_BUDGET_PCT["short_momentum"]),
}
PARK_TICKER = "214980"
PARK_NAME = "KODEX 단기채권PLUS"


@dataclass
class StrategyCandidate:
    strategy_id: str
    strategy_label: str
    ticker: str
    name: str
    weight_pct: float | None = None
    role: str = ""
    note: str = ""
    # 가계 추천스택=100 기준 절대 비중 (ops 지도용 · 합산 집행 아님)
    portfolio_pct: float | None = None
    # 계좌 이분 · 계좌内=100 (연금·ISA / 일반)
    account_id: str = ""
    account_pct: float | None = None


@dataclass
class StrategyCandidatesBundle:
    as_of: str
    market: str
    review_only: bool = True
    writes_target: bool = False
    by_strategy: dict[str, list[StrategyCandidate]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    # 계좌별 가계% 합 (합≈100)
    account_budget_pct: dict[str, float] = field(default_factory=dict)


def snapshot_path(root: Path) -> Path:
    return Path(root) / REPORT_REL


def _row_name(row: Any) -> str:
    return str(
        getattr(row, "name", None)
        or getattr(row, "ticker_name", None)
        or getattr(row, "ticker", "")
        or ""
    )


def _soft_candidates(
    strategy_id: str,
    label: str,
    rows: Sequence[Any],
    *,
    role: str,
) -> list[StrategyCandidate]:
    out: list[StrategyCandidate] = []
    for r in rows or []:
        tk = norm_ticker(getattr(r, "ticker", None))
        if not tk:
            continue
        w = getattr(r, "weight_pct", None)
        try:
            wp = float(w) if w is not None and str(w).strip() != "" else None
        except (TypeError, ValueError):
            wp = None
        out.append(
            StrategyCandidate(
                strategy_id=strategy_id,
                strategy_label=label,
                ticker=tk,
                name=_row_name(r),
                weight_pct=wp,
                role=role,
                note="확인① 정량 후 Soft 통과 · target 사람만",
            )
        )
    return out


def _etf_static_candidates(root: Path, strategy_id: str, label: str) -> list[StrategyCandidate]:
    from alpha_system.shadow.household_alloc_lab import load_recipes

    try:
        raw = load_recipes(root)
    except Exception:  # noqa: BLE001
        return []
    for stg in raw.get("strategies") or []:
        if not isinstance(stg, dict) or str(stg.get("id")) != strategy_id:
            continue
        if str(stg.get("kind")) != "static":
            continue
        out: list[StrategyCandidate] = []
        for sl in stg.get("sleeves") or []:
            if not isinstance(sl, dict):
                continue
            tk = norm_ticker(sl.get("ticker"))
            if not tk:
                continue
            try:
                pct = float(sl.get("pct") or 0)
            except (TypeError, ValueError):
                pct = None
            is_body = strategy_id in ("compass_fit", "static_book")
            out.append(
                StrategyCandidate(
                    strategy_id=strategy_id,
                    strategy_label=label,
                    ticker=tk,
                    name=str(sl.get("name") or tk),
                    weight_pct=pct,
                    role="가계 본체 ETF" if is_body else "Lab 정적 후보",
                    note=(
                        "본체 70~85% 감각 · 앱 밖 · 연 리밸 · Soft합산 금지"
                        if is_body
                        else "Lab 참고 · 본체(나침반적합) 아님 · 앱 밖"
                    ),
                )
            )
        return out
    return []


def _dual_candidates(root: Path, label: str) -> list[StrategyCandidate]:
    """듀얼: GEM 시그널 현재픽 + 유니버스."""
    from alpha_system.ui.services.dual_momentum_ops import compute_dual_momentum_signal

    sig = compute_dual_momentum_signal(root, ensure_fetch=False)
    out: list[StrategyCandidate] = []
    if sig.ok and sig.pick_ticker:
        out.append(
            StrategyCandidate(
                strategy_id="dual_momentum",
                strategy_label=label,
                ticker=sig.pick_ticker,
                name=sig.pick_name or sig.pick_ticker,
                weight_pct=100.0,
                role=f"선택위성 픽 · {sig.pick_role}",
                note=(
                    (sig.reason_ko or "월말 GEM")
                    + " · 슬리브 0~15% · Soft합산 금지"
                ),
            )
        )
    for a in sig.assets:
        if a.ticker == sig.pick_ticker:
            continue
        out.append(
            StrategyCandidate(
                strategy_id="dual_momentum",
                strategy_label=label,
                ticker=a.ticker,
                name=a.name or a.ticker,
                weight_pct=None,
                role=a.role,
                note="GEM 유니버스 · 현재 픽 아님",
            )
        )
    return out


def build_strategy_candidates(
    root: Path,
    *,
    market: str,
    mid_soft_rows: Sequence[Any] | None = None,
    short_prop_rows: Sequence[Any] | None = None,
) -> StrategyCandidatesBundle:
    root = Path(root)
    mkt = str(market or "KOSPI").upper()
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    by: dict[str, list[StrategyCandidate]] = {}
    label_by = {s.strategy_id: s.nav_label for s in STRATEGY_OP_SPECS}

    by["mid_soft"] = _soft_candidates(
        "mid_soft",
        label_by.get("mid_soft", "중기 Soft"),
        list(mid_soft_rows or []),
        role="알파 Soft · 위성 10~20%",
    )
    by["short_momentum"] = _soft_candidates(
        "short_momentum",
        label_by.get("short_momentum", "단기 모멘텀"),
        list(short_prop_rows or []),
        role="단기 위성 0~5%",
    )
    from alpha_system.ui.services.static_book_ops import (
        OPS_BODY_RECIPE,
        STATIC_RECIPE_IDS,
        recommend_static_recipe,
        static_recipe_meta,
    )

    name_by = {m["id"]: m["name_ko"] for m in static_recipe_meta(root)}
    for sid in STATIC_RECIPE_IDS:
        by[sid] = _etf_static_candidates(
            root, sid, name_by.get(sid, sid)
        )
    rec = recommend_static_recipe(root)
    if rec not in (OPS_BODY_RECIPE, "compass_fit"):
        # 운영 추천 스택: 본체는 나침반적합 고정(성적 1등 승격 금지)
        rec = OPS_BODY_RECIPE if OPS_BODY_RECIPE in by else rec
    body_label = f"{name_by.get(rec, rec)} · 가계본체"
    body = _etf_static_candidates(root, rec, body_label) or list(by.get(rec) or [])
    for c in body:
        c.strategy_id = "static_book"
        c.strategy_label = body_label
        c.role = "가계 본체 ETF"
        c.note = "본체 70~85% 감각 · 앱 밖 · 연 리밸 · Soft합산 금지"
    by["static_book"] = body
    by["dual_momentum"] = _dual_candidates(
        root, label_by.get("dual_momentum", "듀얼모멘텀")
    )

    notes = [
        "포트 유니버스 기본=추천 스택(본체 compass_fit · 듀얼 선택 · Soft · 단기)",
        "Lab 정적 전원은 백테스트/전략탭 참고 · 성적1등≠본체 승격",
        "합산 집행·target 자동 없음 · Soft=포트 · ETF·듀얼=앱 밖",
    ]
    return StrategyCandidatesBundle(
        as_of=as_of,
        market=mkt,
        by_strategy=by,
        notes=notes,
    )


def save_strategy_candidates(root: Path, bundle: StrategyCandidatesBundle) -> Path:
    path = snapshot_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "as_of": bundle.as_of,
        "market": bundle.market,
        "review_only": True,
        "writes_target": False,
        "notes": bundle.notes,
        "by_strategy": {
            k: [asdict(c) for c in v] for k, v in bundle.by_strategy.items()
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def persist_candidates_after_quant(root: Path, *, market: str) -> dict[str, Any]:
    """확인① 성공 후 Soft 바스켓·ETF 후보 스냅샷 · target 불변."""
    out: dict[str, Any] = {"ok": False, "writes_target": False}
    root = Path(root)
    mkt = str(market or "KOSPI").upper()
    try:
        from alpha_system.ui.services.context import load_context

        mid = load_context(root, market=mkt, horizon="mid")
        short = load_context(root, market=mkt, horizon="short")
        bundle = build_strategy_candidates(
            root,
            market=mkt,
            mid_soft_rows=list(getattr(mid, "portfolio_rows", None) or []),
            short_prop_rows=list(getattr(short, "portfolio_rows", None) or []),
        )
        path = save_strategy_candidates(root, bundle)
        out["ok"] = True
        out["path"] = str(path)
        out["mid_n"] = len(bundle.by_strategy.get("mid_soft") or [])
        out["short_n"] = len(bundle.by_strategy.get("short_momentum") or [])
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)[:240]
    return out


# 전략 테마 색 (행 구분) · Soft / 단기 / 정적 레시피 / 듀얼
_THEME_BY_ID: dict[str, str] = {
    "mid_soft": "soft",
    "short_momentum": "short",
    "static_book": "static-pick",
    "compass_fit": "static-pick",
    "sixty_forty": "s6040",
    "all_seasons": "seasons",
    "permanent": "perm",
    "permanent_multi": "perm",
    "golden_butterfly": "butterfly",
    "k_all_weather": "kaw",
    "dual_momentum": "dual",
}

# 테마별 (배경, 강조) · 행 전체가 구분되도록 채도↑
_THEME_COLORS: dict[str, tuple[str, str]] = {
    "soft": ("#c7d7f8", "#1e40af"),
    "short": ("#fbc9a8", "#9a3412"),
    "s6040": ("#b7e4de", "#0f766e"),
    "seasons": ("#b8e6cb", "#166534"),
    "perm": ("#f0d78c", "#854d0e"),
    "butterfly": ("#f0c48a", "#9a3412"),
    "kaw": ("#c5ceda", "#1e293b"),
    "static-pick": ("#a8ddea", "#0e7490"),
    "dual": ("#f0b4c6", "#9f1239"),
    "other": ("#d5dbe3", "#475569"),
}


def theme_slug_for_strategy(strategy_id: str) -> str:
    sid = str(strategy_id or "").strip()
    return _THEME_BY_ID.get(sid, "other")


def theme_colors(slug: str) -> tuple[str, str]:
    return _THEME_COLORS.get(slug, _THEME_COLORS["other"])


def _soft_book_equity_cash_split(root: Path | None = None) -> tuple[float, float]:
    """Soft 장부 안 E/C 힌트 · 기본 50/50 · stance yaml 우선."""
    eq, cash = 50.0, 50.0
    if root is None:
        return eq, cash
    try:
        import yaml

        raw = yaml.safe_load(
            (Path(root) / "data" / "investment_stance.yaml").read_text(
                encoding="utf-8"
            )
        )
        book = ((raw or {}).get("stance") or {}).get("soft_book") or {}
        eq = float(book.get("equity_pct_hint", eq))
        cash = float(book.get("cash_pct_hint", cash))
    except Exception:  # noqa: BLE001
        pass
    s = max(eq, 0.0) + max(cash, 0.0)
    if s <= 0:
        return 50.0, 50.0
    return 100.0 * max(eq, 0.0) / s, 100.0 * max(cash, 0.0) / s


def _norm_weights(cands: Sequence[StrategyCandidate]) -> list[tuple[StrategyCandidate, float]]:
    """전략内 정량비중 → 합 1.0. weight 없으면 등분(유니버스-only 행 제외)."""
    scored: list[tuple[StrategyCandidate, float]] = []
    for c in cands or []:
        if c.weight_pct is None:
            continue
        try:
            w = float(c.weight_pct)
        except (TypeError, ValueError):
            continue
        if w < 0:
            continue
        scored.append((c, w))
    if scored:
        tot = sum(w for _, w in scored) or 1.0
        return [(c, w / tot) for c, w in scored]
    return []


def attach_ops_stack_portfolio_pct(
    bundle: StrategyCandidatesBundle,
    *,
    root: Path | None = None,
) -> StrategyCandidatesBundle:
    """추천스택 후보에 가계=100 절대 포트%를 붙인다 (합≈100 · Review-only)."""
    if root is None:
        root = Path(__file__).resolve().parents[3]
    eq_share, cash_share = _soft_book_equity_cash_split(root)
    for sid in OPS_STACK_IDS:
        for c in bundle.by_strategy.get(sid) or []:
            c.portfolio_pct = None

    allocated = 0.0
    for sid in OPS_STACK_IDS:
        budget = float(OPS_STACK_BUDGET_PCT.get(sid, 0.0))
        if budget <= 0:
            continue
        cands = list(bundle.by_strategy.get(sid) or [])

        if sid == "mid_soft":
            eq_budget = budget * eq_share / 100.0
            cash_budget = budget * cash_share / 100.0
            parts = _norm_weights(cands)
            if parts:
                for c, frac in parts:
                    c.portfolio_pct = round(eq_budget * frac, 2)
                    allocated += float(c.portfolio_pct or 0)
            else:
                # Soft 공집합 → 전액 파킹
                cash_budget = budget
            if cash_budget > 0:
                park = next(
                    (c for c in cands if norm_ticker(c.ticker) == PARK_TICKER),
                    None,
                )
                if park is None:
                    park = StrategyCandidate(
                        strategy_id="mid_soft",
                        strategy_label=(
                            (cands[0].strategy_label if cands else None)
                            or "중기 Soft"
                        ),
                        ticker=PARK_TICKER,
                        name=PARK_NAME,
                        weight_pct=cash_share if parts else 100.0,
                        role="Soft 파킹 · 미집행",
                        note="Soft 미집행·C힌트 → 단기채 파킹 · target 불변",
                        portfolio_pct=round(cash_budget, 2),
                    )
                    cands.append(park)
                    bundle.by_strategy[sid] = cands
                else:
                    park.portfolio_pct = round(
                        float(park.portfolio_pct or 0) + cash_budget, 2
                    )
                allocated += round(cash_budget, 2)
            continue

        if sid == "short_momentum":
            parts = _norm_weights(cands)
            if parts:
                for c, frac in parts:
                    c.portfolio_pct = round(budget * frac, 2)
                    allocated += float(c.portfolio_pct or 0)
            else:
                park = StrategyCandidate(
                    strategy_id="short_momentum",
                    strategy_label="단기 모멘텀",
                    ticker=PARK_TICKER,
                    name=PARK_NAME,
                    weight_pct=100.0,
                    role="단기 파킹 · 공집합",
                    note="단기 Soft 없음 → 단기채 파킹 · target 불변",
                    portfolio_pct=round(budget, 2),
                )
                bundle.by_strategy[sid] = [park]
                allocated += round(budget, 2)
            continue

        if sid == "dual_momentum":
            parts = _norm_weights(cands)
            if parts:
                # 픽만 weight 있음 → 전량
                for c, frac in parts:
                    c.portfolio_pct = round(budget * frac, 2)
                    allocated += float(c.portfolio_pct or 0)
            else:
                # 시그널 없으면 듀얼 예산 파킹
                park = StrategyCandidate(
                    strategy_id="dual_momentum",
                    strategy_label="듀얼모멘텀",
                    ticker=PARK_TICKER,
                    name=PARK_NAME,
                    weight_pct=100.0,
                    role="듀얼 파킹",
                    note="듀얼 픽 없음 → 단기채 파킹",
                    portfolio_pct=round(budget, 2),
                )
                bundle.by_strategy[sid] = [park, *cands]
                allocated += round(budget, 2)
            continue

        # static_book · 본체 레시피 정량%
        parts = _norm_weights(cands)
        for c, frac in parts:
            c.portfolio_pct = round(budget * frac, 2)
            allocated += float(c.portfolio_pct or 0)

    # 반올림 잔여 → 본체 최대 레그에 흡수(합 100 맞추기)
    residual = round(100.0 - allocated, 2)
    if abs(residual) >= 0.01:
        body = list(bundle.by_strategy.get("static_book") or [])
        live = [c for c in body if c.portfolio_pct is not None]
        if live:
            top = max(live, key=lambda x: float(x.portfolio_pct or 0))
            top.portfolio_pct = round(float(top.portfolio_pct or 0) + residual, 2)
    return attach_account_split_pct(bundle)


def attach_account_split_pct(
    bundle: StrategyCandidatesBundle,
) -> StrategyCandidatesBundle:
    """가계 포트%를 연금·ISA / 일반으로 나누고 계좌内=100으로 재계산."""
    budgets = {
        ACCOUNT_PENSION: float(ACCOUNT_BUDGET_PCT[ACCOUNT_PENSION]),
        ACCOUNT_TAXABLE: float(ACCOUNT_BUDGET_PCT[ACCOUNT_TAXABLE]),
    }
    bundle.account_budget_pct = dict(budgets)
    by_acct: dict[str, list[StrategyCandidate]] = {
        ACCOUNT_PENSION: [],
        ACCOUNT_TAXABLE: [],
    }
    for sid in OPS_STACK_IDS:
        acct = STRATEGY_ACCOUNT.get(sid) or ACCOUNT_TAXABLE
        for c in bundle.by_strategy.get(sid) or []:
            c.account_id = acct
            c.account_pct = None
            by_acct.setdefault(acct, []).append(c)

    for acct, cands in by_acct.items():
        budget = float(budgets.get(acct) or 0.0)
        live = [c for c in cands if c.portfolio_pct is not None]
        if budget <= 0 or not live:
            continue
        raw_sum = sum(float(c.portfolio_pct or 0) for c in live)
        if raw_sum <= 0:
            continue
        # 계좌内 % = 가계포트% / 계좌예산 × 100
        allocated = 0.0
        for c in live:
            hh = float(c.portfolio_pct or 0)
            c.account_pct = round(hh / budget * 100.0, 2)
            allocated += float(c.account_pct or 0)
        residual = round(100.0 - allocated, 2)
        if abs(residual) >= 0.01:
            top = max(live, key=lambda x: float(x.account_pct or 0))
            top.account_pct = round(float(top.account_pct or 0) + residual, 2)
    return bundle


def account_summary_line(bundle: StrategyCandidatesBundle) -> str:
    """연금·ISA / 일반 가계% 한 줄."""
    b = bundle.account_budget_pct or dict(ACCOUNT_BUDGET_PCT)
    pen = float(b.get(ACCOUNT_PENSION) or ACCOUNT_BUDGET_PCT[ACCOUNT_PENSION])
    tax = float(b.get(ACCOUNT_TAXABLE) or ACCOUNT_BUDGET_PCT[ACCOUNT_TAXABLE])
    return (
        f"계좌 이분 · {ACCOUNT_LABEL_KO[ACCOUNT_PENSION]} {pen:g}% "
        f"(정적+듀얼) · {ACCOUNT_LABEL_KO[ACCOUNT_TAXABLE]} {tax:g}% "
        f"(Soft+단기) · 각 계좌内=100 · 합산 집행 금지"
    )


def candidates_table_rows(
    bundle: StrategyCandidatesBundle,
    *,
    strategy_id: str | None = None,
    skip_static_book_alias: bool = True,
    ops_stack_only: bool = False,
) -> list[dict[str, str]]:
    """포트 유니버스 기본=ops_stack_only · Lab 전체는 False.

    ops_stack_only: 기존 열 + 선두 **계좌·계좌%·가계%**(구 포트%).
    """
    if ops_stack_only and strategy_id is None:
        attach_ops_stack_portfolio_pct(bundle)

    rows: list[dict[str, str]] = []
    if strategy_id:
        items = [(strategy_id, bundle.by_strategy.get(strategy_id or "", []))]
    elif ops_stack_only:
        # 연금 → 일반 순
        acct_order = (ACCOUNT_PENSION, ACCOUNT_TAXABLE)
        items = []
        for acct in acct_order:
            for sid in OPS_STACK_IDS:
                if STRATEGY_ACCOUNT.get(sid) != acct:
                    continue
                if sid in bundle.by_strategy:
                    items.append((sid, bundle.by_strategy.get(sid, [])))
    else:
        items = list(bundle.by_strategy.items())
        if skip_static_book_alias:
            items = [(sid, cs) for sid, cs in items if sid != "static_book"]
    port_mode = bool(ops_stack_only and strategy_id is None)
    for sid, cands in items:
        for c in cands or []:
            w = "—" if c.weight_pct is None else f"{float(c.weight_pct):g}%"
            row: dict[str, str] = {
                "전략": c.strategy_label or sid or "",
                "역할": c.role,
                "종목": c.name,
                "티커": c.ticker,
                "비중": w,
                "비고": (c.note or "")[:48],
                "_sid": str(sid or c.strategy_id or ""),
            }
            if port_mode:
                acct = c.account_id or STRATEGY_ACCOUNT.get(
                    sid or c.strategy_id, ACCOUNT_TAXABLE
                )
                row["계좌"] = ACCOUNT_LABEL_KO.get(acct, acct)
                row["_acct"] = acct
                if c.account_pct is None:
                    row["계좌%"] = "—"
                    row["_acct_pct"] = ""
                else:
                    row["계좌%"] = f"{float(c.account_pct):g}%"
                    row["_acct_pct"] = str(float(c.account_pct))
                if c.portfolio_pct is None:
                    row["가계%"] = "—"
                    row["포트%"] = "—"
                    row["_port"] = ""
                else:
                    row["가계%"] = f"{float(c.portfolio_pct):g}%"
                    row["포트%"] = row["가계%"]  # 하위호환
                    row["_port"] = str(float(c.portfolio_pct))
            rows.append(row)
    return rows


def _legend_html(slugs_used: set[str]) -> str:
    from html import escape

    labels = {
        "soft": "중기 Soft",
        "short": "단기",
        "static-pick": "본체(나침반적합)",
        "s6040": "60/40",
        "seasons": "올시즌스",
        "perm": "영구",
        "butterfly": "황금나비",
        "kaw": "한국올웨더",
        "dual": "듀얼 위성",
        "other": "기타",
    }
    chips = []
    for slug in (
        "static-pick",
        "dual",
        "soft",
        "short",
        "s6040",
        "seasons",
        "perm",
        "butterfly",
        "kaw",
        "other",
    ):
        if slug not in slugs_used:
            continue
        bg, fg = theme_colors(slug)
        chips.append(
            f'<span class="pf-cand-legend-chip pf-cand-theme-{escape(slug)}" '
            f'style="background:{bg};color:{fg};border-color:{fg}55">'
            f"{escape(labels.get(slug, slug))}</span>"
        )
    if not chips:
        return ""
    return (
        '<div class="pf-cand-legend" aria-label="전략 색 범례">'
        + "".join(chips)
        + "</div>"
    )


def _embedded_theme_css() -> str:
    """st.html 스코프용 · 테마 행 배경을 클래스만으로도 보장."""
    rules: list[str] = []
    for slug, (bg, fg) in _THEME_COLORS.items():
        rules.append(
            f".pf-cand-table tr.pf-cand-theme-{slug} td{{"
            f"background:{bg} !important;border-bottom:1px solid {fg}33}}"
            f".pf-cand-table tr.pf-cand-theme-{slug} td:first-child{{"
            f"color:{fg} !important;font-weight:700;"
            f"border-left:4px solid {fg} !important}}"
            f".pf-cand-legend-chip.pf-cand-theme-{slug}{{"
            f"background:{bg};color:{fg};border-color:{fg}66}}"
        )
    return "<style>" + "".join(rules) + "</style>"


def candidates_section_html(
    bundle: StrategyCandidatesBundle,
    *,
    strategy_id: str | None = None,
    title: str = "투자 후보",
    ops_stack_only: bool = True,
) -> str:
    from html import escape

    rows = candidates_table_rows(
        bundle,
        strategy_id=strategy_id,
        ops_stack_only=ops_stack_only if strategy_id is None else False,
        skip_static_book_alias=not ops_stack_only,
    )
    port_mode = bool(ops_stack_only and strategy_id is None)
    tip_stack = (
        account_summary_line(bundle)
        + " · 가계%=가계합100 · 비중=전략内 · target 자동 없음"
        if port_mode
        else "합산 집행 금지 · Soft=포트 · ETF=앱 밖 · target 자동 없음"
    )
    if not rows:
        return (
            f'<div class="pf-strat-cands"><div class="pf-hh-k">{escape(title)}</div>'
            '<div class="pf-hh-tip">후보 없음 · 확인① 정량 후 다시 보세요 · Soft/target 불변</div>'
            "</div>"
        )
    body = []
    slugs_used: set[str] = set()
    for r in rows[:80]:
        slug = theme_slug_for_strategy(r.get("_sid") or "")
        slugs_used.add(slug)
        bg, fg = theme_colors(slug)
        # td마다 인라인 + 클래스 — st.html에서 행 전체 색 유지
        cell = (
            f'style="background:{bg} !important;'
            f'border-bottom:1px solid {fg}33"'
        )
        first = (
            f'style="background:{bg} !important;color:{fg} !important;'
            f"font-weight:700;border-left:4px solid {fg};"
            f'border-bottom:1px solid {fg}33;padding-left:0.45rem"'
        )
        if port_mode:
            body.append(
                f'<tr class="pf-cand-row pf-cand-theme-{escape(slug)}" '
                f'style="background:{bg}">'
                f'<td class="pf-cand-strat" {first}>{escape(r["계좌"])}</td>'
                f"<td {cell}>{escape(r['계좌%'])}</td>"
                f"<td {cell}>{escape(r.get('가계%') or r['포트%'])}</td>"
                f"<td {cell}>{escape(r['전략'])}</td>"
                f"<td {cell}>{escape(r['역할'])}</td>"
                f"<td {cell}>{escape(r['종목'])}</td>"
                f"<td {cell}>{escape(r['티커'])}</td>"
                f"<td {cell}>{escape(r['비중'])}</td>"
                f'<td class="pf-env-muted" {cell}>{escape(r["비고"])}</td>'
                f"</tr>"
            )
        else:
            body.append(
                f'<tr class="pf-cand-row pf-cand-theme-{escape(slug)}" '
                f'style="background:{bg}">'
                f'<td class="pf-cand-strat" {first}>{escape(r["전략"])}</td>'
                f"<td {cell}>{escape(r['역할'])}</td>"
                f"<td {cell}>{escape(r['종목'])}</td>"
                f"<td {cell}>{escape(r['티커'])}</td>"
                f"<td {cell}>{escape(r['비중'])}</td>"
                f'<td class="pf-env-muted" {cell}>{escape(r["비고"])}</td>'
                f"</tr>"
            )
    if port_mode:
        head = (
            "<thead><tr>"
            '<th style="text-align:left;padding:0.35rem">계좌</th>'
            '<th style="text-align:left;padding:0.35rem">계좌%</th>'
            '<th style="text-align:left;padding:0.35rem">가계%</th>'
            '<th style="text-align:left;padding:0.35rem">전략</th>'
            '<th style="text-align:left;padding:0.35rem">역할</th>'
            '<th style="text-align:left;padding:0.35rem">종목</th>'
            '<th style="text-align:left;padding:0.35rem">티커</th>'
            '<th style="text-align:left;padding:0.35rem">비중</th>'
            '<th style="text-align:left;padding:0.35rem">비고</th>'
            "</tr></thead>"
        )
    else:
        head = (
            "<thead><tr>"
            '<th style="text-align:left;padding:0.35rem">전략</th>'
            '<th style="text-align:left;padding:0.35rem">역할</th>'
            '<th style="text-align:left;padding:0.35rem">종목</th>'
            '<th style="text-align:left;padding:0.35rem">티커</th>'
            '<th style="text-align:left;padding:0.35rem">비중</th>'
            '<th style="text-align:left;padding:0.35rem">비고</th>'
            "</tr></thead>"
        )
    return (
        '<div class="pf-strat-cands" role="region">'
        f"{_embedded_theme_css()}"
        f'<div class="pf-hh-k">{escape(title)}</div>'
        f'<div class="pf-env-muted">as_of {escape(bundle.as_of)} · '
        f"{escape(bundle.market)} · Review-only</div>"
        f"{_legend_html(slugs_used)}"
        '<table class="pf-hh-lab-table pf-cand-table" '
        'style="width:100%;border-collapse:collapse">'
        f"{head}<tbody>"
        + "".join(body)
        + "</tbody></table>"
        f'<div class="pf-hh-tip">{escape(tip_stack)}</div>'
        "</div>"
    )


def render_candidates_section(
    bundle: StrategyCandidatesBundle,
    *,
    strategy_id: str | None = None,
    title: str = "투자 후보",
    ops_stack_only: bool = True,
) -> None:
    """Streamlit 표시 · st.html로 style 보존 (markdown은 style 제거)."""
    import streamlit as st

    html = candidates_section_html(
        bundle,
        strategy_id=strategy_id,
        title=title,
        ops_stack_only=ops_stack_only,
    )
    try:
        st.html(html)
    except Exception:  # noqa: BLE001 — 구버전 폴백
        st.markdown(html, unsafe_allow_html=True)


__all__ = [
    "ACCOUNT_BUDGET_PCT",
    "ACCOUNT_LABEL_KO",
    "ACCOUNT_PENSION",
    "ACCOUNT_TAXABLE",
    "OPS_STACK_BUDGET_PCT",
    "OPS_STACK_IDS",
    "STRATEGY_ACCOUNT",
    "StrategyCandidate",
    "StrategyCandidatesBundle",
    "account_summary_line",
    "attach_account_split_pct",
    "attach_ops_stack_portfolio_pct",
    "build_strategy_candidates",
    "candidates_section_html",
    "candidates_table_rows",
    "persist_candidates_after_quant",
    "render_candidates_section",
    "save_strategy_candidates",
    "snapshot_path",
    "theme_colors",
    "theme_slug_for_strategy",
]
