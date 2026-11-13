"""포트 유니버스 — 중기 Soft·단기·가치·방어·보유 후보 한눈 (Review-only).

점수 합산·target 자동기입 없음. Soft≠관찰 합산. 시장은 호출측 장부만.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any, Mapping, Sequence

from alpha_system.proposal_chart import norm_ticker

MODEL_VERSION = "portfolio-universe-v2"


@dataclass(frozen=True)
class UniverseRow:
    ticker: str
    name: str
    in_mid_soft: bool = False
    in_mid_held: bool = False
    in_short_prop: bool = False
    in_short_held: bool = False
    in_mid_watch: bool = False
    in_value: bool = False
    in_defense: bool = False
    gated: bool = False
    role_ko: str = ""
    metrics_ko: str = ""
    investable: bool = False  # 중기 Soft 축
    # 박홍기(기업해부) · Soft 점수 가산 없음
    today_gieop: bool = False
    in_deep: bool = False
    has_draft: bool = False
    draft_ko: str = ""
    quant_label: str = ""
    gieop_next_ko: str = ""
    verdict_ko: str = ""


@dataclass
class PortfolioUniverseBoard:
    market: str
    rows: list[UniverseRow] = field(default_factory=list)
    n_mid_soft: int = 0
    n_mid_held: int = 0
    n_short: int = 0
    n_value: int = 0
    n_defense: int = 0
    n_observe: int = 0
    n_today_gieop: int = 0
    n_draft: int = 0
    headline_ko: str = ""
    caption_ko: str = (
        "한 시장 후보 한눈 · Soft·단기·관찰·박홍기 축 분리 · "
        "합산 집행·target 자동 없음"
    )
    writes_target: bool = False
    model_version: str = MODEL_VERSION


def _usable_row_name(name: object, ticker: object) -> str:
    from alpha_system.market.ticker_names import is_usable_name

    raw = str(name or "").strip()
    if is_usable_name(raw, ticker):
        return raw
    return ""


def _tk_name_from_rows(rows: Sequence[object] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for r in rows or ():
        tk = norm_ticker(getattr(r, "ticker", None))
        if not tk:
            continue
        name = _usable_row_name(getattr(r, "name", None), tk)
        if name:
            out[tk] = name
    return out


def _score_bit(row: object) -> str:
    for attr in ("total_score", "factor_score_total", "score"):
        raw = getattr(row, attr, None)
        try:
            if raw is None or raw == "":
                continue
            return f"{float(raw):.0f}점"
        except (TypeError, ValueError):
            continue
    return ""


def _role_for(
    *,
    mid_soft: bool,
    mid_held: bool,
    short_prop: bool,
    short_held: bool,
    value: bool,
    defense: bool,
    gated: bool,
    mid_watch: bool,
) -> tuple[str, bool]:
    """Return (role_ko, investable)."""
    if gated and not mid_soft:
        return ("주의 · 정성게이트", False)
    if mid_soft and mid_held:
        return ("중기 Soft · 유지 Review", True)
    if mid_soft:
        return ("중기 Soft · 사 후보", True)
    if mid_held:
        return ("중기 보유만 · 팔/줄이기 Review", False)
    if short_prop and short_held:
        return ("단기 위성 · 유지 Review", False)
    if short_prop:
        return ("단기 위성 · 사 후보", False)
    if short_held:
        return ("단기 보유만 · 축소·교체 Review", False)
    if value and defense:
        return ("관찰 · 가치∩방어 (집행 Soft만)", False)
    if value:
        return ("관찰 · 저평가 (매수 아님)", False)
    if defense:
        return ("관찰 · 방어위성 (Soft 합산 금지)", False)
    if mid_watch:
        return ("중기 후보풀 · Soft 전 관찰", False)
    return ("참고", False)


def enrich_universe_row_names(
    root: Path | str,
    board: PortfolioUniverseBoard,
    *,
    market: str | None = None,
    fetch_missing: bool = True,
) -> PortfolioUniverseBoard:
    """티커만 있는 관찰·유니버스 행에 종목명 보강."""
    from dataclasses import replace

    from alpha_system.market.ticker_names import display_name, resolve_ticker_names

    mkt = str(market or board.market or "KOSPI")
    bare = [
        r.ticker
        for r in board.rows
        if not _usable_row_name(r.name, r.ticker)
    ]
    if not bare:
        return board
    names = resolve_ticker_names(
        Path(root),
        bare,
        market=mkt,
        fetch_missing=fetch_missing,
    )
    rows = [
        replace(r, name=display_name(r.ticker, names))
        if not _usable_row_name(r.name, r.ticker)
        else r
        for r in board.rows
    ]
    return replace(board, rows=rows)


def build_portfolio_universe(
    *,
    market: str,
    mid_soft_rows: Sequence[object] | None = None,
    mid_held_rows: Sequence[object] | None = None,
    short_prop_rows: Sequence[object] | None = None,
    short_held_rows: Sequence[object] | None = None,
    mid_watch_tickers: Sequence[str] | None = None,
    theme_board: Any | None = None,
    name_seed: Mapping[str, str] | None = None,
    root: Path | str | None = None,
    fetch_missing_names: bool = True,
) -> PortfolioUniverseBoard:
    """Merge sleeves into one Review table. No score blend."""
    mid_soft = {
        norm_ticker(getattr(r, "ticker", None))
        for r in (mid_soft_rows or ())
        if norm_ticker(getattr(r, "ticker", None))
    }
    mid_held = {
        norm_ticker(getattr(r, "ticker", None))
        for r in (mid_held_rows or ())
        if norm_ticker(getattr(r, "ticker", None))
    }
    short_prop = {
        norm_ticker(getattr(r, "ticker", None))
        for r in (short_prop_rows or ())
        if norm_ticker(getattr(r, "ticker", None))
    }
    short_held = {
        norm_ticker(getattr(r, "ticker", None))
        for r in (short_held_rows or ())
        if norm_ticker(getattr(r, "ticker", None))
    }
    mid_watch = {
        norm_ticker(t)
        for t in (mid_watch_tickers or ())
        if norm_ticker(t)
    }

    value_set: set[str] = set()
    defense_set: set[str] = set()
    gated_set: set[str] = set()
    metrics_by: dict[str, str] = {}
    theme_names: dict[str, str] = {}

    if theme_board is not None:
        for it in getattr(theme_board, "soft_items", None) or ():
            tk = norm_ticker(getattr(it, "ticker", None))
            if tk:
                mid_soft.add(tk)
                nm = _usable_row_name(getattr(it, "name", None), tk)
                if nm:
                    theme_names[tk] = nm
                m = str(getattr(it, "metrics_ko", "") or "")
                if m:
                    metrics_by[tk] = m
        for it in getattr(theme_board, "value_items", None) or ():
            tk = norm_ticker(getattr(it, "ticker", None))
            if not tk:
                continue
            value_set.add(tk)
            nm = _usable_row_name(getattr(it, "name", None), tk)
            if nm:
                theme_names[tk] = nm
            m = str(getattr(it, "metrics_ko", "") or "")
            if m:
                metrics_by[tk] = (
                    f"{metrics_by[tk]} · {m}" if tk in metrics_by else m
                )
        for it in getattr(theme_board, "defense_items", None) or ():
            tk = norm_ticker(getattr(it, "ticker", None))
            if not tk:
                continue
            defense_set.add(tk)
            nm = _usable_row_name(getattr(it, "name", None), tk)
            if nm:
                theme_names[tk] = nm
            m = str(getattr(it, "metrics_ko", "") or "")
            if m:
                metrics_by[tk] = (
                    f"{metrics_by[tk]} · {m}" if tk in metrics_by else m
                )
        for tk in getattr(theme_board, "gated", None) or ():
            t = norm_ticker(tk)
            if t:
                gated_set.add(t)

    names = dict(name_seed or {})
    names.update({k: v for k, v in theme_names.items() if _usable_row_name(v, k)})
    for src_rows in (
        mid_soft_rows,
        mid_held_rows,
        short_prop_rows,
        short_held_rows,
    ):
        for tk, nm in _tk_name_from_rows(src_rows).items():
            if _usable_row_name(nm, tk):
                names[tk] = nm

    for r in mid_soft_rows or ():
        tk = norm_ticker(getattr(r, "ticker", None))
        if not tk:
            continue
        bit = _score_bit(r)
        if bit:
            metrics_by[tk] = (
                f"중기 Soft {bit}"
                if tk not in metrics_by
                else f"중기 Soft {bit} · {metrics_by[tk]}"
            )
    for r in short_prop_rows or ():
        tk = norm_ticker(getattr(r, "ticker", None))
        if not tk:
            continue
        bit = _score_bit(r)
        if bit:
            metrics_by[tk] = (
                f"단기 {bit}"
                if tk not in metrics_by
                else f"{metrics_by[tk]} · 단기 {bit}"
            )

    all_tk = (
        mid_soft
        | mid_held
        | short_prop
        | short_held
        | value_set
        | defense_set
        | gated_set
        | mid_watch
    )

    if root is not None and all_tk:
        try:
            from alpha_system.market.ticker_names import resolve_ticker_names

            names = resolve_ticker_names(
                Path(root),
                sorted(all_tk),
                market=str(market or "KOSPI"),
                base=names,
                fetch_missing=bool(fetch_missing_names),
            )
        except Exception:  # noqa: BLE001
            pass

    rows: list[UniverseRow] = []
    for tk in all_tk:
        ms = tk in mid_soft
        mh = tk in mid_held
        sp = tk in short_prop
        sh = tk in short_held
        val = tk in value_set
        de = tk in defense_set
        gt = tk in gated_set
        mw = tk in mid_watch and not (ms or mh or sp or sh or val or de)
        role, inv = _role_for(
            mid_soft=ms,
            mid_held=mh,
            short_prop=sp,
            short_held=sh,
            value=val,
            defense=de,
            gated=gt,
            mid_watch=mw or (tk in mid_watch and not ms),
        )
        # watch flag if in pool even when Soft
        in_watch = tk in mid_watch
        nm = _usable_row_name(names.get(tk), tk) or tk
        rows.append(
            UniverseRow(
                ticker=tk,
                name=nm,
                in_mid_soft=ms,
                in_mid_held=mh,
                in_short_prop=sp,
                in_short_held=sh,
                in_mid_watch=in_watch,
                in_value=val,
                in_defense=de,
                gated=gt,
                role_ko=role,
                metrics_ko=metrics_by.get(tk, ""),
                investable=inv,
            )
        )

    def _sort_key(r: UniverseRow) -> tuple:
        return (
            0 if r.today_gieop else 1,
            0 if r.investable else 1,
            0 if (r.in_short_prop or r.in_short_held) else 1,
            0 if (r.in_value or r.in_defense) else 1,
            0 if r.in_mid_held else 1,
            0 if r.in_mid_watch else 1,
            r.ticker,
        )

    rows.sort(key=_sort_key)
    n_observe = sum(
        1
        for r in rows
        if (r.in_value or r.in_defense or r.in_mid_watch)
        and not r.investable
        and not r.in_short_prop
        and not r.in_short_held
    )
    n_short = len(short_prop | short_held)
    board = PortfolioUniverseBoard(
        market=str(market or "KOSPI"),
        rows=rows,
        n_mid_soft=len(mid_soft),
        n_mid_held=len(mid_held),
        n_short=n_short,
        n_value=len(value_set),
        n_defense=len(defense_set),
        n_observe=n_observe,
        headline_ko=(
            f"{market} 유니버스 · Soft {len(mid_soft)} · 단기 {n_short} · "
            f"가치 {len(value_set)} · 방어 {len(defense_set)} · 전체 {len(rows)}"
        ),
    )
    return board


def attach_gieop_to_universe(
    board: PortfolioUniverseBoard,
    *,
    today_picks: Sequence[object] | None = None,
    fusion_rows: Sequence[object] | None = None,
    deep_tickers: Sequence[str] | None = None,
) -> PortfolioUniverseBoard:
    """박홍기 오늘픽·초안·정량·심층을 유니버스 행에 붙인다 (점수 불변)."""
    from dataclasses import replace

    today_by = {
        norm_ticker(getattr(p, "ticker", None)): p
        for p in (today_picks or ())
        if norm_ticker(getattr(p, "ticker", None))
    }
    fusion_by = {
        norm_ticker(getattr(r, "ticker", None)): r
        for r in (fusion_rows or ())
        if norm_ticker(getattr(r, "ticker", None))
    }
    deep = {
        norm_ticker(t)
        for t in (deep_tickers or ())
        if norm_ticker(t)
    }
    extra_names: dict[str, str] = {}
    for src in (today_by, fusion_by):
        for tk, obj in src.items():
            nm = _usable_row_name(getattr(obj, "name", None), tk)
            if nm:
                extra_names[tk] = nm

    known = {r.ticker for r in board.rows}
    rows = list(board.rows)
    for tk in set(today_by) | set(fusion_by) | deep:
        if tk in known:
            continue
        rows.append(
            UniverseRow(
                ticker=tk,
                name=extra_names.get(tk) or tk,
                role_ko="박홍기 후보 · Soft 전 관찰",
            )
        )
        known.add(tk)

    out: list[UniverseRow] = []
    for r in rows:
        pick = today_by.get(r.ticker)
        fus = fusion_by.get(r.ticker)
        draft_ko = ""
        quant = ""
        has_draft = False
        next_ko = ""
        verdict_ko = ""
        if pick is not None:
            draft_ko = str(getattr(pick, "draft_ko", "") or "")
            quant = str(getattr(pick, "quant_label", "") or "")
            next_ko = str(getattr(pick, "next_ko", "") or "")
            has_draft = draft_ko not in {"", "초안없음", "—"}
        if fus is not None:
            d = getattr(fus, "draft", None)
            if d is not None:
                draft_ko = draft_ko or str(getattr(d, "status_ko", "") or "")
                has_draft = True
            q = getattr(fus, "quant", None)
            if q is not None and not quant:
                quant = str(getattr(q, "label", "") or "")
            verdict = getattr(fus, "verdict", None)
            if verdict is not None:
                verdict_ko = str(getattr(verdict, "chip_ko", "") or "")
        today = r.ticker in today_by
        in_deep = r.ticker in deep
        role = r.role_ko
        if today and next_ko:
            role = f"오늘 해부 · {next_ko}"
        elif today:
            role = "오늘 해부 · 박홍기"
        elif in_deep and not r.investable:
            role = role or "심층 관찰 · Soft 전"
        metrics = r.metrics_ko
        bits = []
        if verdict_ko:
            bits.append(verdict_ko)
        if draft_ko:
            bits.append(f"해부 {draft_ko}")
        if quant and quant not in {"—", ""}:
            bits.append(f"정량 {quant}")
        if bits:
            metrics = (
                f"{metrics} · {' · '.join(bits)}" if metrics else " · ".join(bits)
            )
        out.append(
            replace(
                r,
                today_gieop=today,
                in_deep=in_deep,
                has_draft=has_draft or bool(draft_ko and draft_ko != "초안없음"),
                draft_ko=draft_ko,
                quant_label=quant,
                gieop_next_ko=next_ko,
                verdict_ko=verdict_ko,
                role_ko=role,
                metrics_ko=metrics,
                name=(
                    extra_names.get(r.ticker)
                    or _usable_row_name(r.name, r.ticker)
                    or r.ticker
                ),
            )
        )

    def _sort_key(row: UniverseRow) -> tuple:
        return (
            0 if row.today_gieop else 1,
            0 if row.investable else 1,
            0 if row.has_draft else 1,
            0 if (row.in_short_prop or row.in_short_held) else 1,
            row.ticker,
        )

    out.sort(key=_sort_key)
    n_today = sum(1 for r in out if r.today_gieop)
    n_draft = sum(1 for r in out if r.has_draft)
    head = board.headline_ko
    if n_today or n_draft:
        head = (
            f"{board.market} 유니버스 · Soft {board.n_mid_soft} · "
            f"오늘해부 {n_today} · 초안 {n_draft} · 전체 {len(out)}"
        )
    return PortfolioUniverseBoard(
        market=board.market,
        rows=out,
        n_mid_soft=board.n_mid_soft,
        n_mid_held=board.n_mid_held,
        n_short=board.n_short,
        n_value=board.n_value,
        n_defense=board.n_defense,
        n_observe=board.n_observe,
        n_today_gieop=n_today,
        n_draft=n_draft,
        headline_ko=head,
        caption_ko=board.caption_ko,
        writes_target=False,
        model_version=MODEL_VERSION,
    )


def filter_universe_rows(
    rows: Sequence[UniverseRow],
    *,
    mode: str = "all",
) -> list[UniverseRow]:
    """mode: all | soft | short | held | observe | gieop."""
    key = str(mode or "all").strip().lower()
    if key in {"all", "전체", ""}:
        return list(rows)
    if key in {"soft", "중기", "매매"}:
        return [r for r in rows if r.investable or r.in_mid_soft]
    if key in {"short", "단기"}:
        return [r for r in rows if r.in_short_prop or r.in_short_held]
    if key in {"held", "보유"}:
        return [r for r in rows if r.in_mid_held or r.in_short_held]
    if key in {"observe", "관찰"}:
        return [
            r
            for r in rows
            if (r.in_value or r.in_defense or r.in_mid_watch)
            and not r.in_mid_soft
        ]
    if key in {"gieop", "해부", "박홍기"}:
        return [
            r
            for r in rows
            if r.today_gieop or r.has_draft or r.in_deep
        ]
    return list(rows)


def _chips(row: UniverseRow) -> str:
    bits: list[str] = []
    if row.today_gieop:
        bits.append('<span class="pf-uni-chip pf-uni-chip-gieop">오늘해부</span>')
    if row.in_mid_soft:
        bits.append('<span class="pf-uni-chip pf-uni-chip-soft">중기Soft</span>')
    if row.in_mid_held:
        bits.append('<span class="pf-uni-chip pf-uni-chip-hold">중기보유</span>')
    if row.in_short_prop:
        bits.append('<span class="pf-uni-chip pf-uni-chip-short">단기제안</span>')
    if row.in_short_held:
        bits.append('<span class="pf-uni-chip pf-uni-chip-short">단보유</span>')
    if row.in_value:
        bits.append('<span class="pf-uni-chip pf-uni-chip-value">가치</span>')
    if row.in_defense:
        bits.append('<span class="pf-uni-chip pf-uni-chip-defense">방어</span>')
    if row.in_deep:
        bits.append('<span class="pf-uni-chip pf-uni-chip-deep">심층</span>')
    if row.verdict_ko:
        vcls = (
            "pf-uni-chip-draft"
            if "PASS" in row.verdict_ko
            else "pf-uni-chip-warn"
        )
        bits.append(
            f'<span class="pf-uni-chip {vcls}">{escape(row.verdict_ko)}</span>'
        )
    if row.has_draft and row.draft_ko:
        bits.append(
            f'<span class="pf-uni-chip pf-uni-chip-draft">'
            f"해부 {escape(row.draft_ko)}</span>"
        )
    elif row.has_draft:
        bits.append('<span class="pf-uni-chip pf-uni-chip-draft">초안</span>')
    if row.in_mid_watch and not row.in_mid_soft:
        bits.append('<span class="pf-uni-chip pf-uni-chip-watch">후보풀</span>')
    if row.gated:
        bits.append('<span class="pf-uni-chip pf-uni-chip-warn">게이트</span>')
    return "".join(bits)


def portfolio_universe_html(
    board: PortfolioUniverseBoard,
    *,
    rows: Sequence[UniverseRow] | None = None,
) -> str:
    from alpha_system.ui.services.rank_watchboard import naver_name_chart_html

    show = list(rows) if rows is not None else list(board.rows)
    glance = (
        f'<div class="pf-uni-glance pf-uni-glance-6">'
        f'<div class="pf-uni-g"><div class="pf-uni-gv">{board.n_mid_soft}</div>'
        f'<div class="pf-uni-gk">중기 Soft</div></div>'
        f'<div class="pf-uni-g"><div class="pf-uni-gv">{board.n_short}</div>'
        f'<div class="pf-uni-gk">단기</div></div>'
        f'<div class="pf-uni-g"><div class="pf-uni-gv">{board.n_today_gieop}</div>'
        f'<div class="pf-uni-gk">오늘 해부</div></div>'
        f'<div class="pf-uni-g"><div class="pf-uni-gv">{board.n_draft}</div>'
        f'<div class="pf-uni-gk">초안</div></div>'
        f'<div class="pf-uni-g"><div class="pf-uni-gv">{board.n_value}</div>'
        f'<div class="pf-uni-gk">가치</div></div>'
        f'<div class="pf-uni-g"><div class="pf-uni-gv">{len(show)}</div>'
        f'<div class="pf-uni-gk">표시</div></div>'
        f"</div>"
    )
    head = (
        f'<div class="pf-uni-head">'
        f'<div class="pf-uni-title">{escape(board.headline_ko)}</div>'
        f'<div class="pf-uni-cap">{escape(board.caption_ko)}</div>'
        f"</div>"
    )
    if not show:
        return (
            f'<div class="pf-uni">'
            f"{head}{glance}"
            f'<div class="pf-uni-empty">후보 없음 · 확인① 정량 후 다시 보세요</div>'
            f"</div>"
        )
    body_rows: list[str] = []
    for r in show:
        if r.today_gieop:
            tone = "gieop"
        elif r.investable:
            tone = "soft"
        elif r.in_short_prop or r.in_short_held:
            tone = "short"
        else:
            tone = "obs"
        metrics = (
            f'<div class="pf-uni-metrics">{escape(r.metrics_ko)}</div>'
            if r.metrics_ko
            else ""
        )
        next_bit = (
            f'<div class="pf-uni-next">{escape(r.gieop_next_ko)}</div>'
            if r.gieop_next_ko
            else ""
        )
        body_rows.append(
            f'<div class="pf-uni-row pf-uni-row-{tone}">'
            f'<div class="pf-uni-name">{naver_name_chart_html(r.ticker, r.name)}</div>'
            f'<div class="pf-uni-chips">{_chips(r)}</div>'
            f'<div class="pf-uni-role">{escape(r.role_ko)}</div>'
            f"{next_bit}{metrics}"
            f"</div>"
        )
    return (
        f'<div class="pf-uni" role="region" aria-label="투자 유니버스">'
        f"{head}{glance}"
        f'<div class="pf-uni-list">{"".join(body_rows)}</div>'
        f"</div>"
    )


def mid_watch_tickers_from_scoreboard(
    scoreboard_rows: Sequence[object] | None,
    *,
    proposal_tickers: Sequence[str] | None = None,
    held_tickers: Sequence[str] | None = None,
    market: str | None = None,
    horizon: str = "mid",
    max_rows: int | None = None,
) -> list[str]:
    """Top observation pool tickers (display only)."""
    from alpha_system.screen_book import watch_max
    from alpha_system.ui.services.rank_watchboard import build_rank_watchboard

    prop = {norm_ticker(t) for t in (proposal_tickers or ()) if norm_ticker(t)}
    held = {norm_ticker(t) for t in (held_tickers or ()) if norm_ticker(t)}
    cap = int(max_rows) if max_rows is not None else int(watch_max(market, horizon))
    board = build_rank_watchboard(
        list(scoreboard_rows or []),
        proposal_tickers=prop,
        held_tickers=held,
        proposal_band_max=max(1, len(prop) or 5),
        max_rows=cap,
    )
    out: list[str] = []
    for r in board.rows:
        tk = norm_ticker(getattr(r, "ticker", None))
        if tk:
            out.append(tk)
    return out


def render_portfolio_universe_tab(
    mid_ctx: Any,
    short_ctx: Any,
    *,
    root: Path | None = None,
) -> None:
    """Streamlit entry for 포트 · 유니버스 탭 (+ 박홍기 오늘 해부)."""
    import streamlit as st

    from alpha_system.ui.services.gieop_alpha_seed import collect_alpha_gieop_candidates
    from alpha_system.ui.services.gieop_fusion_desk import build_fusion_desk
    from alpha_system.ui.services.gieop_observe_board import (
        build_portfolio_bridge,
        load_observe_ui_board,
        open_path,
        resolve_gieop_paths,
        run_observe_pipe,
    )
    from alpha_system.ui.services.gieop_today_loop import (
        build_today_gieop_loop,
        today_gieop_loop_html,
    )
    from alpha_system.ui.services.portfolio_theme_fusion import (
        build_portfolio_theme_fusion,
    )
    from alpha_system.ui.services.ui_copy import copy_get

    root_path = Path(root or getattr(mid_ctx, "root", Path.cwd()))
    market = str(getattr(mid_ctx, "screen_market", None) or "KOSPI")
    try:
        from alpha_system.screen_book import source_data_dir

        source = source_data_dir(root_path, market)
    except Exception:  # noqa: BLE001
        source = root_path / "data"

    mid_soft = list(getattr(mid_ctx, "portfolio_rows", None) or [])
    mid_held = list(getattr(mid_ctx, "ops_portfolio_rows", None) or [])
    short_prop = list(getattr(short_ctx, "portfolio_rows", None) or [])
    short_held = list(getattr(short_ctx, "ops_portfolio_rows", None) or [])
    soft_tks = [
        norm_ticker(getattr(r, "ticker", None))
        for r in mid_soft
        if norm_ticker(getattr(r, "ticker", None))
    ]
    held_tks = [
        norm_ticker(getattr(r, "ticker", None))
        for r in mid_held
        if norm_ticker(getattr(r, "ticker", None))
    ]

    theme = build_portfolio_theme_fusion(
        root_path,
        market=market,
        soft_rows=mid_soft,
        scoreboard_rows=list(getattr(mid_ctx, "scoreboard_rows", None) or []),
        source_data_dir=source,
    )
    watch = mid_watch_tickers_from_scoreboard(
        getattr(mid_ctx, "scoreboard_rows", None),
        proposal_tickers=[getattr(r, "ticker", "") for r in mid_soft],
        held_tickers=[getattr(r, "ticker", "") for r in mid_held],
        market=market,
        horizon="mid",
    )
    board = build_portfolio_universe(
        market=market,
        mid_soft_rows=mid_soft,
        mid_held_rows=mid_held,
        short_prop_rows=short_prop,
        short_held_rows=short_held,
        mid_watch_tickers=watch,
        theme_board=theme,
        root=root_path,
        fetch_missing_names=True,
    )

    paths = resolve_gieop_paths(root_path)
    observe = load_observe_ui_board(root_path, market=market)
    bridge = build_portfolio_bridge(
        observe.deep_pick, soft_tickers=soft_tks, held_tickers=held_tks
    )
    alpha_board = collect_alpha_gieop_candidates(
        root_path,
        market=market,
        soft_rows=mid_soft,
        held_tickers=held_tks,
        include_value_only=True,
        value_only_max=5,
    )
    fusion = build_fusion_desk(
        root_path,
        market=market,
        candidates=alpha_board.candidates,
    )
    today = build_today_gieop_loop(
        market=market,
        fusion_rows=fusion.rows,
        bridge_rows=bridge.rows,
        deep_pick=observe.deep_pick,
        candidates=alpha_board.candidates,
        max_picks=3,
    )
    deep_tks = [
        norm_ticker(getattr(r, "ticker", None))
        for r in (observe.deep_pick or [])
        if norm_ticker(getattr(r, "ticker", None))
    ]
    board = attach_gieop_to_universe(
        board,
        today_picks=today.picks,
        fusion_rows=fusion.rows,
        deep_tickers=deep_tks,
    )
    try:
        board = enrich_universe_row_names(
            root_path, board, market=market, fetch_missing=True
        )
    except Exception:  # noqa: BLE001
        pass

    st.caption(
        copy_get(
            "portfolio",
            "universe_caption",
            default=(
                "기본=추천스택 · 연금·ISA(정적+듀얼) / 일반(Soft+단기) · "
                "계좌%·가계% · 합산 매수 금지 · target 사람만"
            ),
        )
    )

    # 전략별 투자 후보 (확인①·전략 탭 산출) + 계좌별 할 일·역발상 게이트
    try:
        from alpha_system.ui.services.account_ops_checklist import (
            account_ops_checklist_html,
            build_account_ops_checklist,
        )
        from alpha_system.ui.services.strategy_candidates_board import (
            build_strategy_candidates,
            render_candidates_section,
        )

        _cands = build_strategy_candidates(
            root_path,
            market=market,
            mid_soft_rows=mid_soft,
            short_prop_rows=short_prop,
        )
        _deep_n = len(observe.deep_pick or [])
        _precise = False
        try:
            _counts = getattr(observe, "counts", None) or {}
            if isinstance(_counts, dict):
                _precise = int(_counts.get("정밀관찰") or 0) > 0
        except Exception:  # noqa: BLE001
            _precise = False
        _observe_ok = bool(_deep_n > 0 or _precise) if observe.available else None
        # 해부 PASS 파일은 별도 · 오늘 픽만으로는 HOLD(조사 보류) 힌트
        _gieop = "HOLD" if today.picks else None
        _fear_tone = None
        _fear_av = None
        _fear_miss = None
        try:
            from alpha_system.economy_compass.fear_greed_soft import (
                build_fear_greed_soft_board,
            )

            _fear = build_fear_greed_soft_board(None, root=root_path)
            _fear_tone = str(getattr(_fear, "tone", "") or "") or None
            _fear_av = int(getattr(_fear, "available_n", 0) or 0)
            _fear_miss = int(getattr(_fear, "missing_n", 0) or 0)
        except Exception:  # noqa: BLE001
            _fear_tone = None
        _ops = build_account_ops_checklist(
            _cands,
            observe_deep_or_precise=_observe_ok,
            logic_or_essence_ok=True if mid_soft else None,
            gieop_gate=_gieop,
            fear_tone=_fear_tone,
            fear_as_buy_signal=False,
            soft_funded_from_pension=False,
            fear_available_n=_fear_av,
            fear_missing_n=_fear_miss,
            pass_value=True if mid_soft else None,
        )
        st.caption(
            copy_get(
                "portfolio",
                "account_ops_caption",
                default=(
                    "연금·ISA=정적+듀얼(앱 밖) · 일반=Soft+단기 · "
                    "합산 주문 금지 · 역발상=게이트 Review"
                ),
            )
        )
        try:
            st.html(account_ops_checklist_html(_ops))
        except Exception:  # noqa: BLE001
            st.markdown(
                account_ops_checklist_html(_ops), unsafe_allow_html=True
            )
        render_candidates_section(
            _cands,
            title=copy_get(
                "portfolio",
                "sec_strategy_cands",
                default="전략별 투자 후보 · 연금·ISA / 일반",
            ),
        )
    except Exception as exc:  # noqa: BLE001
        st.caption(f"전략 후보 표시 생략 · {exc}")

    # 박홍기 블록 — 지도(유니버스) 위 돋보기
    st.markdown(
        f'<div class="pf-uni-gieop-h">'
        f'{escape(copy_get("portfolio", "sec_gieop", default="오늘 해부 · 박홍기"))}'
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        copy_get(
            "portfolio",
            "universe_gieop_caption",
            default=(
                "아래 2~3종만 박홍기에서 해부 · Soft·target 불변 · "
                "할 일 확인 후 중기 Soft·HTS"
            ),
        )
    )
    st.markdown(today_gieop_loop_html(today), unsafe_allow_html=True)
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        if st.button(
            copy_get("portfolio", "gieop_btn_pipe", default="① 관찰 파이프"),
            key=f"uni_gieop_pipe_{market}",
            use_container_width=True,
            type="primary",
            help="저PBR→시드→정량커버 · Soft·target 불변",
        ):
            pipe = run_observe_pipe(
                root_path,
                market=market,
                soft_rows=mid_soft,
                soft_tickers=soft_tks,
                held_tickers=held_tks,
            )
            st.success(
                copy_get(
                    "portfolio",
                    "gieop_pipe_ok",
                    default=(
                        "파이프 완료 · 시드 {n}/{s} · 정량 {q} "
                        "(↑{h}/中{m}/↓{l}) · 아래 카드·표 확인"
                    ),
                    n=pipe["seed_new"],
                    s=pipe["seed_skip"],
                    q=pipe["quant_n"],
                    h=pipe["quant_hi"],
                    m=pipe["quant_mid"],
                    l=pipe["quant_lo"],
                )
            )
            st.rerun()
    with c2:
        if st.button(
            copy_get("portfolio", "gieop_btn_open", default="② 박홍기 열기"),
            key=f"uni_gieop_open_{market}",
            use_container_width=True,
            disabled=not paths.start_ok,
            help="시작하기.html · 위 종목 JSON만 해부",
        ):
            err = open_path(paths.start_html)
            if err:
                st.warning(err)
            else:
                st.caption(str(paths.start_html))
    with c3:
        if st.button(
            copy_get("portfolio", "gieop_btn_drafts", default="내조사 폴더"),
            key=f"uni_gieop_drafts_{market}",
            use_container_width=True,
            disabled=not paths.drafts_ok,
        ):
            err = open_path(paths.drafts_dir)
            if err:
                st.warning(err)
    if not paths.start_ok:
        st.caption(
            copy_get(
                "portfolio",
                "gieop_missing",
                default=(
                    "시작하기.html 없음 · data/local/gieop_paths.json 에 "
                    "gieop_root 지정"
                ),
            )
        )

    filter_labels = (
        copy_get("portfolio", "universe_filter_all", default="전체"),
        copy_get("portfolio", "universe_filter_soft", default="중기 Soft"),
        copy_get("portfolio", "universe_filter_gieop", default="해부"),
        copy_get("portfolio", "universe_filter_short", default="단기"),
        copy_get("portfolio", "universe_filter_held", default="보유"),
        copy_get("portfolio", "universe_filter_observe", default="관찰"),
    )
    mode_map = {
        filter_labels[0]: "all",
        filter_labels[1]: "soft",
        filter_labels[2]: "gieop",
        filter_labels[3]: "short",
        filter_labels[4]: "held",
        filter_labels[5]: "observe",
    }
    picked = st.segmented_control(
        copy_get("portfolio", "universe_filter_label", default="유니버스 필터"),
        options=list(filter_labels),
        selection_mode="single",
        required=True,
        key=f"pf_universe_filter_{market}",
        label_visibility="collapsed",
        width="stretch",
    )
    mode = mode_map.get(str(picked or filter_labels[0]), "all")
    filtered = filter_universe_rows(board.rows, mode=mode)
    st.markdown(
        portfolio_universe_html(board, rows=filtered),
        unsafe_allow_html=True,
    )
