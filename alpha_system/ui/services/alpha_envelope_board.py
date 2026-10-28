"""알파 통합 장부 비중 — 중기·단기·방어·파킹 (SAA 별개 · 9:1 고정 아님).

Soft 미집행·공격 0% 잔여는 공중 대기가 아니라 동일 단기채에 파킹한다.
나침반 stage → 개별주 E / 단기채 C 후:
  중기 = E × MID_OF_EQUITY(0.90)
  단기 = E × SHORT_OF_EQUITY(0.10)
  방어 = C → KODEX 단기채권PLUS

Review-only · target_portfolio·자동주문 불변 · Core score_m 제외 유지.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Optional, Sequence

from alpha_system.economy_signal import (
    EnvelopePolicy,
    envelope_policy,
    load_cached_signal,
    policy_target_line,
)
from alpha_system.ui.services.alpha_book_ops import (
    AlphaBookOpsPolicy,
    load_alpha_book_ops,
)

# SoT: 개별주 안 중기/위성 분할 (yaml satellite_of_equity는 문서용)
MID_OF_EQUITY = 0.90
SHORT_OF_EQUITY = 0.10


@dataclass(frozen=True)
class UnifiedSleeves:
    """정책 3슬리브 % (알파북=100)."""

    stage: Optional[int]
    stage_label: str
    equity_pct: float
    cash_pct: float
    mid_pct: float
    short_pct: float
    cash_ticker: str
    cash_name: str
    policy_line: str
    mid_of_equity: float = MID_OF_EQUITY
    short_of_equity: float = SHORT_OF_EQUITY

    @property
    def mid_share(self) -> float:
        return float(self.mid_pct) / 100.0

    @property
    def short_share(self) -> float:
        return float(self.short_pct) / 100.0

    @property
    def cash_share(self) -> float:
        return float(self.cash_pct) / 100.0


@dataclass(frozen=True)
class AlphaEnvelopeAlloc:
    """나침반 정책 + 오늘 Soft/추세 반영 집행 (통합 3슬리브)."""

    stage: Optional[int]
    stage_label: str
    policy_equity_pct: float
    policy_cash_pct: float
    policy_mid_pct: float
    policy_short_pct: float
    mid_deploy_pct: Optional[float]
    short_deploy_pct: Optional[float]
    proposal_equity_pct: float
    waiting_pct: float
    cash_ticker: str
    cash_name: str
    soft_empty: bool
    policy_line: str
    active_horizon: str = "mid"  # mid | short — 현재 탭 상세
    review_only: bool = True

    @property
    def undrawn_equity_pct(self) -> float:
        return max(0.0, float(self.policy_equity_pct) - float(self.proposal_equity_pct))

    @property
    def undrawn_mid_pct(self) -> float:
        if self.mid_deploy_pct is None:
            return 0.0
        return max(0.0, float(self.policy_mid_pct) - float(self.mid_deploy_pct))

    @property
    def undrawn_short_pct(self) -> float:
        if self.short_deploy_pct is None:
            return 0.0
        return max(0.0, float(self.policy_short_pct) - float(self.short_deploy_pct))


def resolve_envelope_policy(root: Path | None = None) -> EnvelopePolicy:
    """Cached EconomySignal stage → envelope. Missing → fail-open 90/10."""
    base = Path(root) if root is not None else Path(".")
    sig = load_cached_signal(base)
    if sig is None:
        return envelope_policy(None)
    return envelope_policy(sig.stage)


def resolve_equity_cash_shares(
    root: Path | None = None,
) -> tuple[float, float, EnvelopePolicy]:
    """Returns (equity_share, cash_share, policy) — total equity sleeve before mid/short split."""
    pol = resolve_envelope_policy(root)
    return float(pol.equity_share), float(pol.cash_share), pol


def _satellite_of_equity(book: AlphaBookOpsPolicy) -> float:
    raw = book.raw.get("book") if isinstance(book.raw, dict) else None
    if isinstance(raw, dict) and raw.get("satellite_of_equity") is not None:
        try:
            v = float(raw["satellite_of_equity"])
            if 0.0 < v < 1.0:
                return v
        except (TypeError, ValueError):
            pass
    return float(SHORT_OF_EQUITY)


def load_strategy_posture(root: Path | None = None) -> dict:
    """data/strategy_portfolio.yaml 의 posture(선택). 없으면 {}."""
    base = Path(root) if root is not None else Path(".")
    path = base / "data" / "strategy_portfolio.yaml"
    if not path.is_file():
        return {}
    try:
        import yaml  # type: ignore

        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(raw, dict):
        return {}
    posture = raw.get("posture")
    return dict(posture) if isinstance(posture, dict) else {}


def resolve_unified_sleeves(root: Path | None = None) -> UnifiedSleeves:
    """나침반 E/C × 개별주 안 중기90/단기10.

    strategy_portfolio.posture.equity_pct / cash_pct 가 있으면 국면 E/C를 덮어쓴다
    (현실적 중립 · Review-only · target 불변).
    """
    base = Path(root) if root is not None else Path(".")
    book = load_alpha_book_ops(base)
    eq_share, cash_share, pol = resolve_equity_cash_shares(base)
    posture = load_strategy_posture(base)
    stage_label = str(pol.label or "")
    policy_line = policy_target_line(pol.stage)
    if posture.get("equity_pct") is not None and posture.get("cash_pct") is not None:
        try:
            eq_pct_ov = float(posture["equity_pct"])
            cash_pct_ov = float(posture["cash_pct"])
            if eq_pct_ov + cash_pct_ov > 99.5 and eq_pct_ov + cash_pct_ov < 100.5:
                eq_share = eq_pct_ov / 100.0
                cash_share = cash_pct_ov / 100.0
                stage_label = (
                    f"{stage_label} · 자세 E{eq_pct_ov:g}/C{cash_pct_ov:g}".strip(" ·")
                )
                policy_line = (
                    f"자세 고정 개별주 {eq_pct_ov:g}% / 단기채 {cash_pct_ov:g}% "
                    f"(나침반 stage={pol.stage} 참고만)"
                )
        except (TypeError, ValueError):
            pass
    sat = _satellite_of_equity(book)
    mid_frac = max(0.0, 1.0 - sat)
    eq_pct = round(eq_share * 100.0, 1)
    cash_pct = round(cash_share * 100.0, 1)
    mid_pct = round(eq_share * mid_frac * 100.0, 1)
    short_pct = round(eq_share * sat * 100.0, 1)
    # 반올림 드리프트 → cash에 흡수하지 않고 mid에 미세 조정
    drift = round(100.0 - (mid_pct + short_pct + cash_pct), 1)
    if abs(drift) >= 0.05:
        mid_pct = round(mid_pct + drift, 1)
    return UnifiedSleeves(
        stage=pol.stage,
        stage_label=stage_label,
        equity_pct=eq_pct,
        cash_pct=cash_pct,
        mid_pct=mid_pct,
        short_pct=short_pct,
        cash_ticker=str(book.cash_ticker),
        cash_name=str(book.cash_name),
        policy_line=policy_line,
        mid_of_equity=mid_frac,
        short_of_equity=sat,
    )


def _sum_weight_pct(rows: Sequence[object] | None) -> float:
    prop_pct_raw = 0.0
    for row in rows or ():
        try:
            w = getattr(row, "weight_pct", None)
            if w is None:
                extra = getattr(row, "extra", None) or {}
                if isinstance(extra, dict):
                    w = extra.get("weight_pct") or extra.get("weight")
            if w is not None:
                prop_pct_raw += float(w)
        except (TypeError, ValueError):
            continue
    if 0 < prop_pct_raw <= 1.5:
        prop_pct_raw *= 100.0
    return round(max(0.0, min(100.0, prop_pct_raw)), 1)


def build_alpha_envelope_alloc(
    proposal_rows: Sequence[object] | None,
    *,
    root: Path | None = None,
    book_policy: AlphaBookOpsPolicy | None = None,
    short_proposal_rows: Sequence[object] | None = None,
    mid_proposal_rows: Sequence[object] | None = None,
    active_horizon: str = "mid",
) -> AlphaEnvelopeAlloc:
    """통합 정책 + 오늘 집행. mid/short 행을 넘기면 각각 합산, 아니면 proposal=활성 탭."""
    _ = book_policy  # cash from unified sleeves
    base = Path(root) if root is not None else Path(".")
    sleeves = resolve_unified_sleeves(base)
    hz = "short" if str(active_horizon or "").lower() in {"short", "s"} else "mid"

    mid_dep: Optional[float]
    short_dep: Optional[float]
    if mid_proposal_rows is not None and short_proposal_rows is not None:
        mid_dep = _sum_weight_pct(mid_proposal_rows)
        short_dep = _sum_weight_pct(short_proposal_rows)
    elif mid_proposal_rows is not None:
        mid_dep = _sum_weight_pct(mid_proposal_rows)
        short_dep = (
            _sum_weight_pct(short_proposal_rows)
            if short_proposal_rows is not None
            else None
        )
    elif short_proposal_rows is not None:
        short_dep = _sum_weight_pct(short_proposal_rows)
        mid_dep = None
    elif hz == "short":
        short_dep = _sum_weight_pct(proposal_rows)
        mid_dep = None
    else:
        mid_dep = _sum_weight_pct(proposal_rows)
        short_dep = None

    known = [x for x in (mid_dep, short_dep) if x is not None]
    prop_pct = round(sum(known), 1) if known else 0.0
    if hz == "short":
        soft_empty = short_dep is not None and short_dep <= 0.05
    else:
        soft_empty = mid_dep is not None and mid_dep <= 0.05
    # 활성 탭만 로드 시: 대기 = 100 − 활성 집행 (타 슬리브·방어 포함 Review)
    # 양쪽 로드 시: 대기 = 100 − (중기+단기 집행)
    if mid_dep is not None and short_dep is not None:
        waiting = round(max(0.0, 100.0 - prop_pct), 1)
    else:
        active = short_dep if hz == "short" else mid_dep
        waiting = round(100.0 - float(active or 0.0), 1)
    return AlphaEnvelopeAlloc(
        stage=sleeves.stage,
        stage_label=sleeves.stage_label,
        policy_equity_pct=sleeves.equity_pct,
        policy_cash_pct=sleeves.cash_pct,
        policy_mid_pct=sleeves.mid_pct,
        policy_short_pct=sleeves.short_pct,
        mid_deploy_pct=mid_dep,
        short_deploy_pct=short_dep,
        proposal_equity_pct=prop_pct,
        waiting_pct=waiting,
        cash_ticker=sleeves.cash_ticker,
        cash_name=sleeves.cash_name,
        soft_empty=soft_empty,
        policy_line=sleeves.policy_line,
        active_horizon=hz,
    )


@dataclass(frozen=True)
class BookSlideSeg:
    """100% 가로 바 한 칸 — 방어 | 공격 종목 | 파킹(대기=동일 단기채)."""

    label: str
    pct: float
    kind: str  # defense | attack | park
    ticker: str = ""
    title: str = ""  # hover


def _attack_segs_from_rows(
    rows: Sequence[object] | None,
    *,
    sleeve_tag: str,
) -> tuple[list[BookSlideSeg], float]:
    segs: list[BookSlideSeg] = []
    attack_sum = 0.0
    for row in rows or ():
        try:
            w = getattr(row, "weight_pct", None)
            if w is None:
                continue
            pct = float(w)
        except (TypeError, ValueError):
            continue
        if pct <= 0.05:
            continue
        tk = str(getattr(row, "ticker", "") or "").zfill(6)
        name = str(getattr(row, "name", "") or tk).strip() or tk
        short_name = name if len(name) <= 6 else name[:5] + "…"
        segs.append(
            BookSlideSeg(
                label=f"{sleeve_tag}{short_name} {pct:g}%",
                pct=round(pct, 1),
                kind="attack",
                ticker=tk,
                title=f"공격·{sleeve_tag} {name} ({tk}) {pct:g}%",
            )
        )
        attack_sum += pct
    return segs, round(attack_sum, 1)


def build_book_slide_segments(
    proposal_rows: Sequence[object] | None,
    *,
    root: Path | None = None,
    active_horizon: str = "mid",
    mid_proposal_rows: Sequence[object] | None = None,
    short_proposal_rows: Sequence[object] | None = None,
) -> tuple[list[BookSlideSeg], UnifiedSleeves]:
    """오늘 제안 종목%(공격) + 잔여% = 100.

    잔여(미집행·Soft 공집합)는 **공중 대기가 아니라** 정책 방어와 동일
    단기채에 파킹한다. 표시만 정책C / Soft파킹으로 나눈다.
    """
    sleeves = resolve_unified_sleeves(root)
    segs: list[BookSlideSeg] = []
    attack_sum = 0.0
    if mid_proposal_rows is not None or short_proposal_rows is not None:
        m_segs, m_sum = _attack_segs_from_rows(mid_proposal_rows, sleeve_tag="중·")
        s_segs, s_sum = _attack_segs_from_rows(short_proposal_rows, sleeve_tag="단·")
        segs.extend(m_segs)
        segs.extend(s_segs)
        attack_sum = round(m_sum + s_sum, 1)
    else:
        tag = "단·" if str(active_horizon).lower() in {"short", "s"} else "중·"
        a_segs, attack_sum = _attack_segs_from_rows(proposal_rows, sleeve_tag=tag)
        segs.extend(a_segs)
    rest = round(max(0.0, 100.0 - attack_sum), 1)
    # 정책 방어(C) + Soft 미집행분 → 전부 동일 단기채 파킹
    cash = min(rest, float(sleeves.cash_pct))
    park = round(max(0.0, rest - cash), 1)
    cash_lab = f"{sleeves.cash_name} ({sleeves.cash_ticker})"
    if cash >= 0.05:
        segs.append(
            BookSlideSeg(
                label=f"방어 {cash:g}%",
                pct=cash,
                kind="defense",
                ticker=sleeves.cash_ticker,
                title=(
                    f"방어 · {cash_lab} {cash:g}% · 정책 C={sleeves.cash_pct:g}%"
                ),
            )
        )
    if park >= 0.05:
        segs.append(
            BookSlideSeg(
                label=f"파킹 {park:g}%",
                pct=park,
                kind="park",
                ticker=sleeves.cash_ticker,
                title=(
                    f"파킹 · Soft/추세 미집행 {park:g}% → 동일 {cash_lab} "
                    f"(공중 대기 금지 · 정책 개별주 예산 {sleeves.equity_pct:g}%)"
                ),
            )
        )
    if not segs:
        segs.append(
            BookSlideSeg(
                label=f"파킹·방어 100%",
                pct=100.0,
                kind="defense",
                ticker=sleeves.cash_ticker,
                title=f"공격 0% · 전액 {cash_lab} 파킹",
            )
        )
    # 반올림 보정
    total = sum(s.pct for s in segs)
    if abs(total - 100.0) >= 0.05 and segs:
        last = segs[-1]
        segs[-1] = BookSlideSeg(
            label=last.label,
            pct=round(last.pct + (100.0 - total), 1),
            kind=last.kind,
            ticker=last.ticker,
            title=last.title,
        )
    return segs, sleeves


_ATTACK_COLORS = (
    "#2563eb",
    "#7c3aed",
    "#db2777",
    "#ea580c",
    "#0891b2",
    "#4f46e5",
    "#c026d3",
    "#0d9488",
)


def _seg_bar_html(
    segs: Sequence[BookSlideSeg],
    *,
    colors: Sequence[str] | None = None,
    label_min_pct: float = 3.5,
) -> tuple[str, list[str]]:
    """가로 트랙 HTML + 공격 칸에 쓴 색 목록(범례용)."""
    parts: list[str] = []
    attack_colors: list[str] = []
    ai = 0
    palette = list(colors) if colors else list(_ATTACK_COLORS)
    for s in segs:
        w = max(0.0, float(s.pct))
        if w < 0.05:
            continue
        if s.kind == "defense":
            bg = "var(--pf-slide-defense, #64748b)"
        elif s.kind in {"park", "wait"}:
            # 파킹=동일 단기채 · 색만 정책 방어와 구분
            bg = "var(--pf-slide-park, #78716c)"
        else:
            bg = palette[ai % len(palette)]
            attack_colors.append(bg)
            ai += 1
        if w >= label_min_pct:
            show = escape(s.label)
        elif w >= 1.5:
            show = escape(f"{w:g}%")
        else:
            show = ""
        parts.append(
            f'<div class="pf-slide-seg" style="width:{w:g}%;flex:0 0 {w:g}%;'
            f'background:{bg};" title="{escape(s.title or s.label)}">'
            f'<span class="pf-slide-seg-lab">{show}</span></div>'
        )
    return "".join(parts), attack_colors


def book_slide_bar_html(
    segs: Sequence[BookSlideSeg],
    *,
    sleeves: UnifiedSleeves | None = None,
) -> str:
    """포트 최상위 100% 가로 슬라이드 바 + 공격(주식) 종목 세부."""
    track_html, attack_colors = _seg_bar_html(segs, label_min_pct=3.5)
    attack_segs = [s for s in segs if s.kind == "attack" and s.pct >= 0.05]
    attack_sum = round(sum(s.pct for s in attack_segs), 1)

    # 범례 — 공격은 칸 색과 동일 점
    legend_bits: list[str] = []
    ai = 0
    for s in segs:
        if s.pct < 0.05:
            continue
        if s.kind == "attack":
            bg = attack_colors[ai] if ai < len(attack_colors) else _ATTACK_COLORS[0]
            ai += 1
            legend_bits.append(
                f'<span class="pf-slide-leg-item">'
                f'<span class="pf-slide-dot" style="background:{bg}"></span>'
                f"공격 · {escape(s.label)}</span>"
            )
        else:
            kind_ko = (
                "방어"
                if s.kind == "defense"
                else ("파킹" if s.kind in {"park", "wait"} else s.kind)
            )
            dot_cls = (
                "pf-slide-dot-defense"
                if s.kind == "defense"
                else "pf-slide-dot-park"
            )
            legend_bits.append(
                f'<span class="pf-slide-leg-item">'
                f'<span class="pf-slide-dot {dot_cls}"></span>'
                f"{escape(kind_ko)} · {escape(s.label)}"
                f'{(" · " + escape(s.ticker)) if s.ticker else ""}</span>'
            )

    # 공격자산 안 = 100% (종목 상대 비중)
    attack_block = ""
    if attack_segs and attack_sum >= 0.05:
        inner: list[BookSlideSeg] = []
        for s in attack_segs:
            share = round(100.0 * float(s.pct) / attack_sum, 1)
            # 라벨: 중·삼성 42% 처럼 내부%
            base = s.label.rsplit(" ", 1)[0] if " " in s.label else s.label
            inner.append(
                BookSlideSeg(
                    label=f"{base} {share:g}%",
                    pct=share,
                    kind="attack",
                    ticker=s.ticker,
                    title=(
                        f"{s.title or s.label} · 알파북 {s.pct:g}% "
                        f"· 공격자산 안 {share:g}%"
                    ),
                )
            )
        # 반올림 보정
        itot = sum(x.pct for x in inner)
        if abs(itot - 100.0) >= 0.05 and inner:
            last = inner[-1]
            inner[-1] = BookSlideSeg(
                label=last.label,
                pct=round(last.pct + (100.0 - itot), 1),
                kind=last.kind,
                ticker=last.ticker,
                title=last.title,
            )
        inner_html, _ = _seg_bar_html(inner, colors=attack_colors, label_min_pct=4.0)
        detail_rows = "".join(
            f'<div class="pf-slide-atk-row">'
            f'<span class="pf-slide-dot" style="background:'
            f'{attack_colors[i] if i < len(attack_colors) else _ATTACK_COLORS[0]}">'
            f"</span>"
            f'<span class="pf-slide-atk-name">{escape(s.label)}</span>'
            f'<span class="pf-slide-atk-pct">알파북 <b>{s.pct:g}%</b></span>'
            f'<span class="pf-slide-atk-share">공격 안 '
            f"<b>{inner[i].pct:g}%</b></span>"
            f"</div>"
            for i, s in enumerate(attack_segs)
        )
        attack_block = (
            f'<div class="pf-slide-atk">'
            f'<div class="pf-slide-k">공격(주식) {attack_sum:g}%'
            f'<span class="pf-env-muted"> · 안쪽 바=공격자산 100%</span></div>'
            f'<div class="pf-slide-track pf-slide-track-atk">{inner_html}</div>'
            f'<div class="pf-slide-atk-list">{detail_rows}</div>'
            f"</div>"
        )
    elif not attack_segs:
        park_n = round(sum(s.pct for s in segs if s.kind in {"park", "defense"}), 1)
        cash_hint = ""
        if sleeves is not None:
            cash_hint = f" · {escape(sleeves.cash_name)} ({escape(sleeves.cash_ticker)})"
        attack_block = (
            '<div class="pf-slide-atk pf-slide-atk-empty">'
            f"공격(주식) 0% · 미집행 {park_n:g}%는 단기채에 파킹"
            f"{cash_hint} · Soft 통과 전 공중 대기 금지"
            "</div>"
        )

    stage = ""
    if sleeves is not None and sleeves.stage is not None:
        stage = (
            f" · {sleeves.stage}단계 정책 "
            f"중기{sleeves.mid_pct:g}/단기{sleeves.short_pct:g}/방어{sleeves.cash_pct:g}"
        )
    return (
        '<div class="pf-slide" role="img" '
        'aria-label="알파북 100퍼센트 방어·공격·파킹 비중">'
        f'<div class="pf-slide-k">목표 구성 · 알파 위성 100%'
        f'<span class="pf-env-muted">{escape(stage)}</span></div>'
        f'<div class="pf-slide-track">{track_html}</div>'
        f'<div class="pf-slide-legend">{"".join(legend_bits)}</div>'
        f"{attack_block}"
        '<div class="pf-slide-tip">'
        "이렇게 구성: 공격=제안 종목 · 방어=정책 단기채 · "
        "파킹=Soft 미집행(같은 단기채) · 계좌 % 맞춤 아님 · "
        "매매 순서는 위 「오늘 매매」·아래 집합 · Review-only</div>"
        "</div>"
    )


def alpha_envelope_html(alloc: AlphaEnvelopeAlloc) -> str:
    """포트 ③ 통합 스트립 — 중기·단기·방어."""
    stage_s = (
        f"{alloc.stage}단계 · {escape(alloc.stage_label)}"
        if alloc.stage is not None
        else "단계 미산출 · 기본 설계"
    )
    cash_lab = escape(f"{alloc.cash_name} ({alloc.cash_ticker})")
    policy = (
        f"정책: 중기 <b>{alloc.policy_mid_pct:g}%</b> · "
        f"단기 <b>{alloc.policy_short_pct:g}%</b> · "
        f"방어 <b>{alloc.policy_cash_pct:g}%</b>"
        f' <span class="pf-env-muted">(개별주 {alloc.policy_equity_pct:g}% '
        f"안 중기90/단기10 · 9:1 고정 아님)</span>"
    )
    def _dep(v: Optional[float], label: str) -> str:
        if v is None:
            return f"{label} <b>—</b>"
        return f"{label} <b>{v:g}%</b>"

    if alloc.soft_empty and (
        (alloc.active_horizon == "short" and (alloc.short_deploy_pct or 0) <= 0.05)
        or (alloc.active_horizon != "short" and (alloc.mid_deploy_pct or 0) <= 0.05)
    ):
        deploy = (
            f"오늘 집행 Review({escape(alloc.active_horizon)}): 제안 <b>0%</b> · "
            f"미집행 <b>{alloc.waiting_pct:g}%</b> → "
            f"{cash_lab} <b>파킹</b> (신규 매수 보류 · 공중 대기 금지)"
        )
    else:
        bits = [
            _dep(alloc.mid_deploy_pct, "중기"),
            _dep(alloc.short_deploy_pct, "단기"),
            f"파킹·방어 <b>{alloc.waiting_pct:g}%</b>",
        ]
        deploy = "오늘 Soft/추세 반영: " + " · ".join(bits)
        undrawn_bits = []
        if alloc.mid_deploy_pct is not None and alloc.undrawn_mid_pct >= 0.5:
            undrawn_bits.append(f"중기 미충족 {alloc.undrawn_mid_pct:g}%p")
        if alloc.short_deploy_pct is not None and alloc.undrawn_short_pct >= 0.5:
            undrawn_bits.append(f"단기 미충족 {alloc.undrawn_short_pct:g}%p")
        if undrawn_bits:
            deploy += (
                " · " + escape(" · ".join(undrawn_bits)) + f"→{cash_lab} 파킹"
            )
    tip = (
        f"{escape(alloc.policy_line)}. "
        f"방어·파킹={cash_lab} · Soft 미집행도 동일 단기채 · "
        f"CMA/예수금 동일 역할 · 중기 QVM / 단기 60·120·score_m 분리 · "
        f"SAA 별개 · target·자동주문 없음."
    )
    return (
        '<div class="pf-env-strip" role="status">'
        f'<div class="pf-env-k">알파 통합 장부 · {escape(stage_s)}</div>'
        f'<div class="pf-env-policy">{policy}</div>'
        f'<div class="pf-env-deploy">{deploy}</div>'
        f'<div class="pf-env-tip">{tip}</div>'
        "</div>"
    )


__all__ = [
    "MID_OF_EQUITY",
    "SHORT_OF_EQUITY",
    "AlphaEnvelopeAlloc",
    "BookSlideSeg",
    "UnifiedSleeves",
    "alpha_envelope_html",
    "book_slide_bar_html",
    "build_alpha_envelope_alloc",
    "build_book_slide_segments",
    "resolve_envelope_policy",
    "resolve_equity_cash_shares",
    "load_strategy_posture",
    "resolve_unified_sleeves",
]
