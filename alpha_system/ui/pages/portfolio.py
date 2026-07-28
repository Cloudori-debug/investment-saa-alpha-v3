"""Portfolio detail — holdings input + proposal_book with take-profit cues."""

from __future__ import annotations

from datetime import date as _date

import streamlit as st

from alpha_system.schema import TrancheId
from alpha_system.scoring.engine import NameScore
from alpha_system.sizing.allocate import allocate_tranche
from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.cecs_workbench import (
    build_relative_cutoff_ladder,
    confirm_score_cutoff,
    default_relative_cutoff_rank,
)
from alpha_system.ui.services.nav import FOCUS_HOLDINGS_INPUT, consume_focus
from alpha_system.ui.services.portfolio_widgets import render_portfolio_bullets
from alpha_system.ui.services.rank_watchboard import build_rank_watchboard
from alpha_system.ui.services.ui_copy import copy_get

# Initial §7.5 review band (not unlocked to 30).
_TARGET_NAMES_MIN = 5
_TARGET_NAMES_MAX = 8
_TARGET_NAMES_DEFAULT = 6
_WATCH_MAX = 30


def render_portfolio(ctx: DashboardContext) -> None:
    focus = consume_focus()
    # Primary job of this page — keep picker open after restart / sidebar nav.
    if focus == FOCUS_HOLDINGS_INPUT:
        st.session_state["holdings_input_open"] = True
    if "holdings_input_open" not in st.session_state:
        st.session_state["holdings_input_open"] = True
    _render_holdings_input(ctx)
    _render_ops_holdings_guide(ctx)

    with st.container(border=True):
        st.subheader("포트폴리오 리뷰")
        st.caption(
            "제안 북(스크린) · 익절: 유지/줄이기/환금(절반)/전량 · "
            "행 펼침 상세 · target 자동 변경 없음 · Review-only"
        )
        st.caption(
            "proposal_book · 매입 비중 없음 · 도달=절반 환금 · "
            "탈락·4주 미상향=전량 · 자동매도 없음"
        )
        _render_sector_exposure(ctx)
        _render_revalidate_flags(ctx)
        _render_cutoff_and_count(ctx)
        _render_rank_watchboard(ctx)
        if not ctx.portfolio_rows:
            st.info(
                "적격(eligibility) 통과 종목이 없어 제안 북을 표시할 수 없습니다. "
                "위 절대 컷오프·편입 수를 확인하거나 CECS final·alpha_scores를 점검하세요."
            )
        else:
            st.markdown("#### 제안 북")
            render_portfolio_bullets(ctx, mode="full", key_prefix="pf_proposal")


def _render_ops_holdings_guide(ctx: DashboardContext) -> None:
    """Per-holding guide; expander opens evidence for the recommendation."""
    from alpha_system.ui.services.rotation_compass import (
        BEARING_KO,
        build_rotation_compass,
        evidence_lines_for_row,
    )

    ops = list(ctx.ops_portfolio_rows or [])
    proposal_tks = {str(r.ticker).zfill(6) for r in (ctx.portfolio_rows or [])}
    by_tk = {str(r.ticker).zfill(6): r for r in ops}
    compass = build_rotation_compass(ops)
    with st.container(border=True):
        st.subheader("실투자 포트 · 종목별 안내")
        st.caption(
            "줄을 눌러 근거 확인 · 실보유 기준 · 자동매매 없음 · "
            "순위만↓=유지 · 전량·교체=제안탈락·논지·타임캡"
        )
        if not compass.items:
            st.markdown(
                "알파 실보유가 없습니다. 위에서 **내 보유종목 선택 → 후보에서 선택**으로 "
                "종목을 고르세요 (수량 불필요)."
            )
            return
        for i in compass.items:
            title = f"{i.name} ({i.ticker}) — {BEARING_KO[i.bearing]}"
            if i.step_id and i.step_id != "HOLD":
                title += f" · {i.step_id}"
            with st.expander(title, expanded=False):
                row = by_tk.get(i.ticker)
                if row is None:
                    st.caption(i.detail or i.label)
                    continue
                in_prop = i.ticker in proposal_tks
                for line in evidence_lines_for_row(row, in_proposal=in_prop):
                    st.markdown(f"- {line}")


def _current_alpha_paste(ctx: DashboardContext) -> str:
    from alpha_system.ui.services.holdings_input import (
        HoldingDraft,
        format_drafts_as_paste,
    )

    drafts: list[HoldingDraft] = []
    for r in ctx.ops_portfolio_rows or []:
        drafts.append(
            HoldingDraft(
                ticker=str(r.ticker).zfill(6),
                quantity=0.0,  # filled below from positions if needed
                avg_price=r.avg_price,
                name=str(r.name or ""),
            )
        )
    # Prefer live CSV quantities
    path = ctx.root / "data" / "positions.csv"
    if path.exists():
        import pandas as pd

        try:
            df = pd.read_csv(path, dtype=str)
            if not df.empty and "asset_group" in df.columns:
                kr = df[df["asset_group"].astype(str) == "kr_alpha"]
                drafts = []
                for _, row in kr.iterrows():
                    try:
                        q = float(row.get("quantity") or 0)
                    except (TypeError, ValueError):
                        q = 0.0
                    try:
                        ap = (
                            float(row["avg_price"])
                            if str(row.get("avg_price") or "").strip()
                            else None
                        )
                    except (TypeError, ValueError):
                        ap = None
                    drafts.append(
                        HoldingDraft(
                            ticker=str(row.get("ticker") or "").zfill(6),
                            quantity=q,
                            avg_price=ap,
                            name=str(row.get("name") or ""),
                        )
                    )
        except Exception:
            pass
    return format_drafts_as_paste(drafts)


def _render_holdings_input(ctx: DashboardContext) -> None:
    from alpha_system.ui.services.holdings_input import (
        drafts_from_tickers,
        parse_holdings_paste,
        upsert_kr_alpha_positions,
    )

    # Bordered block (not only a collapsed expander) so the picker stays visible.
    with st.container(border=True):
        st.subheader("내 보유종목 선택")
        st.caption(
            "적격 후보 ≤30 안 슬라이더로 고르기 (수량 불필요) · "
            "또는 HTS 붙여넣기 · kr_alpha만 갱신 · 현금/ETF 유지 · target·자동매매 없음"
        )
        # Apply pending text BEFORE instantiating the text_area widget.
        pending = st.session_state.pop("holdings_paste_pending", None)
        if pending is not None:
            st.session_state["holdings_paste_text"] = pending
        elif "holdings_paste_text" not in st.session_state:
            st.session_state["holdings_paste_text"] = _current_alpha_paste(ctx)

        tab_pick, tab_paste, tab_help = st.tabs(["후보에서 선택", "붙여넣기", "안내"])
        with tab_pick:
            _render_holdings_candidate_pick(ctx)
        with tab_paste:
            text = st.text_area(
                "보유 목록",
                key="holdings_paste_text",
                height=160,
                placeholder="030200 100 45000\n021240 50 52000",
                label_visibility="collapsed",
            )
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button(
                    "저장하고 나침반 갱신",
                    type="primary",
                    key="holdings_save",
                    use_container_width=True,
                ):
                    parsed = parse_holdings_paste(text)
                    if parsed.errors and not parsed.drafts:
                        for e in parsed.errors:
                            st.error(e)
                    else:
                        for e in parsed.errors:
                            st.warning(e)
                        path = ctx.root / "data" / "positions.csv"
                        result = upsert_kr_alpha_positions(
                            path,
                            parsed.drafts,
                            root=ctx.root,
                            replace_alpha=True,
                        )
                        st.session_state["holdings_input_open"] = True
                        st.session_state["holdings_paste_pending"] = format_drafts_helper(
                            parsed.drafts
                        )
                        st.success(
                            f"알파 {result['alpha_count']}종 저장 · "
                            f"기타 {result['kept_other']}행 유지"
                        )
                        st.rerun()
            with c2:
                if st.button(
                    "제안 초안",
                    key="holdings_from_proposal",
                    use_container_width=True,
                    help="제안 종목 코드를 칸에만 채움 · 수량은 직접 입력",
                ):
                    tickers = [r.ticker for r in (ctx.portfolio_rows or [])]
                    drafts = drafts_from_tickers(tickers, root=ctx.root)
                    lines = [f"{d.ticker} " for d in drafts]
                    st.session_state["holdings_paste_pending"] = "\n".join(lines)
                    st.session_state["holdings_input_open"] = True
                    st.rerun()
            with c3:
                if st.button(
                    "알파 비우기",
                    key="holdings_clear_alpha",
                    use_container_width=True,
                ):
                    path = ctx.root / "data" / "positions.csv"
                    upsert_kr_alpha_positions(
                        path, [], root=ctx.root, replace_alpha=True
                    )
                    st.session_state["holdings_paste_pending"] = ""
                    st.session_state["holdings_input_open"] = True
                    st.rerun()

            preview = parse_holdings_paste(
                st.session_state.get("holdings_paste_text") or ""
            )
            if preview.drafts:
                st.caption(
                    f"인식 {len(preview.drafts)}종"
                    + (f" · 경고 {len(preview.errors)}" if preview.errors else "")
                )
        with tab_help:
            st.markdown(
                "- **후보에서 선택**: 슬라이더·세부 선택 후 **「선택 종목 등록」** 필수\n"
                "- 아래 표/목록을 직접 고쳐도 저장되지 않습니다\n"
                "- 수량이 필요하면 **붙여넣기** 탭: `030200 100 45000`\n"
                "- 저장 시 **kr_alpha만** 교체, 현금·ETF는 그대로\n"
                "- 평가액 0 행은 시세 갱신 대상에는 포함, 비중 계산에서는 제외"
            )


def _saved_kr_alpha_rows(ctx: DashboardContext) -> list[dict[str, object]]:
    """Read kr_alpha rows from positions.csv (includes qty=0 placeholders)."""
    import pandas as pd

    path = ctx.root / "data" / "positions.csv"
    if not path.exists():
        return []
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception:
        return []
    if df.empty or "ticker" not in df.columns:
        return []
    if "asset_group" in df.columns:
        df = df[df["asset_group"].astype(str) == "kr_alpha"]
    out: list[dict[str, object]] = []
    for _, row in df.iterrows():
        raw = str(row.get("ticker") or "").strip()
        if not raw:
            continue
        tk = raw.zfill(6) if raw.isdigit() else raw
        try:
            qty = float(row.get("quantity") or 0)
        except (TypeError, ValueError):
            qty = 0.0
        out.append(
            {
                "ticker": tk,
                "name": str(row.get("name") or tk),
                "quantity": qty,
            }
        )
    return out


def _render_holdings_candidate_pick(ctx: DashboardContext) -> None:
    """Pick holdings from eligible rank watchboard (≤30) via rank-range slider."""
    from alpha_system.ui.services.holdings_input import (
        drafts_from_tickers,
        upsert_kr_alpha_positions,
    )

    saved = _saved_kr_alpha_rows(ctx)
    saved_tickers = {str(r["ticker"]) for r in saved}

    with st.container(border=True):
        st.markdown("**지금 저장된 알파**")
        if not saved:
            st.caption("아직 없음 · 아래에서 고른 뒤 「선택 종목 등록」을 누르세요")
        else:
            names = [f"{r['name']} ({r['ticker']})" for r in saved]
            st.caption(" · ".join(names))
            st.caption(f"{len(saved)}종 저장됨 · 새로고침해도 유지 · 수량 없음 OK")

    proposal_tickers = {str(r.ticker) for r in (ctx.portfolio_rows or [])}
    board = build_rank_watchboard(
        ctx.scoreboard_rows or [],
        proposal_tickers=proposal_tickers,
        held_tickers=saved_tickers,
        proposal_band_max=int(ctx.cfg.sizing.target_names),
        max_rows=30,
    )
    rows = list(board.rows)
    if not rows:
        st.info("점수판 적격 후보가 없습니다. 점수판을 먼저 확인하세요.")
        return

    n_max = len(rows)
    band = int(ctx.cfg.sizing.target_names)
    default_hi = min(band, n_max)

    st.markdown("**후보에서 고르기**")
    st.caption(
        "아래 표는 미리보기입니다(직접 편집 불가). "
        "슬라이더·세부 선택으로 고른 뒤 반드시 「선택 종목 등록」을 누르세요."
    )

    lo, hi = st.slider(
        "순위 구간 (적격 후보)",
        min_value=1,
        max_value=n_max,
        value=(1, default_hi),
        key="holdings_cand_rank_range",
        help=f"적격 점수 순위 1~{n_max} 안 · 섹터캡 미적용 참고 순위",
    )
    labels = [f"{r.rank:02d} · {r.name} ({r.ticker})" for r in rows]
    label_to_ticker = {lab: r.ticker for lab, r in zip(labels, rows)}
    ticker_to_label = {r.ticker: lab for lab, r in zip(labels, rows)}
    range_labels = [lab for lab, r in zip(labels, rows) if lo <= r.rank <= hi]
    saved_labels = [
        ticker_to_label[tk] for tk in saved_tickers if tk in ticker_to_label
    ]

    pending_sel = st.session_state.pop("holdings_cand_sel_pending", None)
    if pending_sel is not None:
        st.session_state["holdings_cand_sel"] = pending_sel
        st.session_state["holdings_cand_range_applied"] = (lo, hi)
    elif "holdings_cand_sel" not in st.session_state:
        # Prefer already-saved names so refresh does not look like a wipe.
        st.session_state["holdings_cand_sel"] = (
            saved_labels if saved_labels else range_labels
        )
        st.session_state["holdings_cand_range_applied"] = (lo, hi)
    else:
        prev_range = st.session_state.get("holdings_cand_range_applied")
        if prev_range != (lo, hi):
            st.session_state["holdings_cand_sel"] = range_labels
            st.session_state["holdings_cand_range_applied"] = (lo, hi)

    selected_labels = st.multiselect(
        "세부 선택 (등록할 종목)",
        options=labels,
        key="holdings_cand_sel",
        help="슬라이더 구간을 바꾸면 그 구간으로 선택이 바뀝니다. 저장은 아래 버튼으로만 됩니다.",
    )
    tickers = [label_to_ticker[lab] for lab in selected_labels if lab in label_to_ticker]

    st.caption(f"지금 고른 종목 {len(tickers)}종 (아직 저장 전일 수 있음)")

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button(
            "선택 종목 등록",
            type="primary",
            key="holdings_cand_save",
            use_container_width=True,
            disabled=not tickers,
        ):
            drafts = drafts_from_tickers(tickers, root=ctx.root)
            path = ctx.root / "data" / "positions.csv"
            result = upsert_kr_alpha_positions(
                path,
                drafts,
                root=ctx.root,
                replace_alpha=True,
                keep_zero_qty=True,
                keep_existing_meta=True,
            )
            # Keep picker on what was just saved (not slider default).
            st.session_state["holdings_cand_sel_pending"] = [
                ticker_to_label[t] for t in tickers if t in ticker_to_label
            ]
            st.session_state["holdings_input_open"] = True
            st.session_state["holdings_paste_pending"] = _current_alpha_paste(ctx)
            st.success(
                f"알파 {result['alpha_count']}종 저장 완료 · "
                f"현금/ETF {result['kept_other']}행 유지"
            )
            st.rerun()
    with b2:
        if st.button(
            "저장된 목록으로 되돌리기",
            key="holdings_cand_reset_saved",
            use_container_width=True,
            disabled=not saved_labels,
            help="세부 선택을 지금 저장된 알파로 맞춥니다",
        ):
            st.session_state["holdings_cand_sel_pending"] = saved_labels
            st.session_state["holdings_input_open"] = True
            st.rerun()
    with b3:
        if st.button(
            "알파 비우기",
            key="holdings_cand_clear",
            use_container_width=True,
        ):
            path = ctx.root / "data" / "positions.csv"
            upsert_kr_alpha_positions(path, [], root=ctx.root, replace_alpha=True)
            st.session_state["holdings_paste_pending"] = ""
            st.session_state["holdings_cand_sel_pending"] = []
            st.session_state["holdings_input_open"] = True
            st.rerun()


def format_drafts_helper(drafts) -> str:
    from alpha_system.ui.services.holdings_input import format_drafts_as_paste

    return format_drafts_as_paste(drafts)


def _render_rank_watchboard(ctx: DashboardContext) -> None:
    """Display-only eligible rank board (≤30). Not a buy/sell signal.

    Does not mark positions.csv holdings — ops book is not used for this board.
    """
    proposal_tickers = {str(r.ticker).zfill(6) for r in (ctx.portfolio_rows or [])}
    band = int(ctx.cfg.sizing.target_names)
    board = build_rank_watchboard(
        ctx.scoreboard_rows or [],
        proposal_tickers=proposal_tickers,
        held_tickers=set(),  # positions.csv 보유 표시 사용 안 함
        proposal_band_max=band,
        max_rows=_WATCH_MAX,
    )

    with st.container(border=True):
        st.subheader(
            copy_get("portfolio", "watchboard_title", default="적격 순위 감시")
        )
        st.caption(
            copy_get(
                "portfolio",
                "watchboard_caption",
                default=(
                    "표시만 · 매수/매도 지시 아님 · 편입 수(5~8)와 별개 · "
                    "positions 보유 미표시 · "
                    f"{board.basis}"
                ),
            )
        )
        for w in board.warnings:
            st.warning(w)
        if not board.rows:
            st.info("감시 보드에 표시할 적격 종목이 없습니다.")
            return

        in_prop = sum(1 for r in board.rows if r.in_proposal)
        st.markdown(
            f"- 적격 전체 **{board.eligible_count}**종 · 보드 **{len(board.rows)}**종"
            f" (상한 {board.max_rows}) · 제안 밴드 **1~{board.proposal_band_max}**위\n"
            f"- 보드 안 제안 북 표시: **{in_prop}**종"
        )

        table_rows = []
        for r in board.rows:
            flags = []
            if r.in_proposal:
                flags.append("제안")
            if r.rank > board.proposal_band_max and r.in_proposal:
                flags.append("밴드밖")
            table_rows.append(
                {
                    "순위": r.rank,
                    "티커": r.ticker,
                    "이름": r.name,
                    "total": r.total_score,
                    "섹터": r.sector or "—",
                    "표시": " · ".join(flags) if flags else "—",
                }
            )
        st.dataframe(
            table_rows,
            use_container_width=True,
            hide_index=True,
            height=min(420, 48 + 28 * len(table_rows)),
        )

        st.caption(
            copy_get(
                "portfolio",
                "watchboard_footer",
                default=(
                    "순위 하락 ≠ 매도 트리거. 제안 탈락 시 익절 배지(S2a)는 별도 권고입니다. "
                    "positions.csv 보유 하이라이트는 사용하지 않습니다."
                ),
            )
        )


def _render_sector_exposure(ctx: DashboardContext) -> None:
    from alpha_system.ui.services.sector_exposure import assess_sector_weight_caps
    from alpha_system.ui.services.ui_copy import copy_get

    rows = ctx.portfolio_rows or []
    if not rows:
        return
    exposures = assess_sector_weight_caps(rows, data_dir=ctx.root / "data")
    overs = [e for e in exposures if e.over]
    if overs:
        for e in overs:
            tickers = ", ".join(e.tickers)
            st.warning(
                copy_get(
                    "portfolio",
                    "sector_cap_over",
                    default=(
                        f"섹터 합산 {e.bucket} {e.weight_pct}% > 한도 {e.limit_pct}% "
                        f"({e.name_count}종: {tickers}) — 비중·편입 재검토"
                    ),
                    bucket=e.bucket,
                    weight=f"{e.weight_pct:.1f}",
                    limit=f"{e.limit_pct:.0f}",
                    tickers=tickers,
                    n=str(e.name_count),
                )
            )
    else:
        limit = exposures[0].limit_pct if exposures else 35.0
        st.caption(
            copy_get(
                "portfolio",
                "sector_cap_ok",
                default=(
                    f"섹터 합산 한도 {limit:.0f}% 이내 "
                    f"(동일 섹터 ≤2종 · 2종 이상 시 합산 ≤{limit:.0f}%)"
                ),
                limit=f"{limit:.0f}",
            )
        )


def _render_revalidate_flags(ctx: DashboardContext) -> None:
    flagged = [
        r
        for r in (ctx.portfolio_rows or [])
        if (r.extra or {}).get("revalidate_required")
    ]
    if not flagged:
        return
    lines = []
    for r in flagged:
        reason = (r.extra or {}).get("revalidate_reason") or "목표가 재검증 필요"
        as_of = (r.extra or {}).get("approved_as_of") or "—"
        lines.append(f"`{r.ticker}` {r.name}: {reason} (승인 {as_of})")
    st.warning("목표가 재검증\n\n" + "\n\n".join(lines))


def _render_cutoff_and_count(ctx: DashboardContext) -> None:
    """Absolute cutoff first, then portfolio count in the 5~8 band."""
    scored = [
        {
            "ticker": row.ticker,
            "name": row.name,
            "total_score": row.total_score,
        }
        for row in ctx.scoreboard_rows
        if row.total_score is not None
    ]
    # Ladder from rank 1 so any absolute cutoff on the board can be chosen.
    ladder = build_relative_cutoff_ladder(scored, min_rank=1)
    current_n = int(ctx.cfg.sizing.target_names)
    current_cutoff = ctx.cfg.scoring.score_cutoff
    cutoff_label = f"{current_cutoff:g}" if current_cutoff is not None else "미확정"

    with st.expander(
        f"절대 컷오프·편입 수 — 현재 cutoff {cutoff_label} / {current_n}종",
        expanded=not ctx.portfolio_rows,
    ):
        st.caption(
            "초기 설계: **절대 score_cutoff → eligibility → 상위 편입 수(5~8, 기본 6)**. "
            "종목 수를 먼저 고르고 그 점수를 컷으로 만드는 상대순위 방식은 쓰지 않습니다. "
            "확정 전에는 설정과 제안 북이 바뀌지 않으며 `target_portfolio.csv`도 변경하지 않습니다."
        )
        if not ladder:
            st.warning("컷오프를 계산할 유효 스코어가 없습니다.")
            return

        by_rank = {option.rank_n: option for option in ladder}
        suggested_rank = default_relative_cutoff_rank(ladder)
        # Prefer the ladder step nearest the current absolute cutoff.
        if current_cutoff is not None:
            suggested_rank = min(
                by_rank.values(),
                key=lambda option: abs(option.cutoff - float(current_cutoff)),
            ).rank_n

        cutoff_key = "portfolio_absolute_cutoff_rank"
        if cutoff_key not in st.session_state or int(st.session_state[cutoff_key]) not in by_rank:
            st.session_state[cutoff_key] = suggested_rank

        natural = [option for option in ladder if option.is_natural_break]
        if natural:
            st.markdown("**① 절대 score_cutoff — 점수 단절점 참고**")
            labels = {
                option.rank_n: (
                    f"cutoff {option.cutoff:.2f} · 적격 {option.eligible_count}종"
                    + (
                        f" · 갭 {option.margin_below:.2f}"
                        if option.margin_below is not None
                        else ""
                    )
                )
                for option in natural
            }
            break_ranks = [option.rank_n for option in natural]
            radio_index = (
                break_ranks.index(suggested_rank)
                if suggested_rank in break_ranks
                else 0
            )
            picked = st.radio(
                "단절점 고르기",
                options=break_ranks,
                format_func=lambda rank: labels[rank],
                index=radio_index,
                key="portfolio_cutoff_natural_break",
            )
            if st.button("단절점을 컷오프 슬라이더에 적용", key="portfolio_apply_break"):
                st.session_state[cutoff_key] = picked
                st.rerun()

        cutoff_rank = st.slider(
            "① 절대 score_cutoff (경계 순위 기준)",
            min_value=ladder[0].rank_n,
            max_value=ladder[-1].rank_n,
            step=1,
            key=cutoff_key,
            help=(
                "선택한 순위의 total_score가 절대 컷오프가 됩니다. "
                "이 값 이상만 eligibility=True입니다."
            ),
        )
        cutoff_opt = by_rank[int(cutoff_rank)]
        st.markdown(
            f"- 절대 `score_cutoff`: **{cutoff_opt.cutoff:.2f}**\n"
            f"- 이 컷을 통과하는 적격: **{cutoff_opt.eligible_count}종**\n"
            f"- 경계: `{cutoff_opt.boundary_ticker}` {cutoff_opt.boundary_name}"
            + (
                f"\n- 바로 아래: `{cutoff_opt.next_ticker}` {cutoff_opt.next_name} "
                f"· {cutoff_opt.next_score:.2f} · 갭 **{cutoff_opt.margin_below:.2f}**"
                if cutoff_opt.next_ticker is not None
                and cutoff_opt.next_score is not None
                and cutoff_opt.margin_below is not None
                else ""
            )
        )

        st.markdown("**② 제안 북 편입 수 (초기 설계 5~8, 기본 6)**")
        count_key = "portfolio_target_names_band"
        initial_n = min(max(current_n, _TARGET_NAMES_MIN), _TARGET_NAMES_MAX)
        if count_key not in st.session_state:
            st.session_state[count_key] = initial_n
        target_n = st.slider(
            "적격 종목 중 제안 북에 담을 최대 종목 수",
            min_value=_TARGET_NAMES_MIN,
            max_value=_TARGET_NAMES_MAX,
            step=1,
            key=count_key,
            help=(
                "테마 상관이 높아 종목을 많이 늘려도 논지 리스크는 크게 줄지 않습니다. "
                "초기 §7.5 검토 범위는 5~8, 권고·기본은 6입니다."
            ),
        )
        if target_n != _TARGET_NAMES_DEFAULT:
            st.caption(
                f"기본 정책은 {_TARGET_NAMES_DEFAULT}종입니다. "
                f"{target_n}종은 5~8 밴드 내 운영 조정입니다."
            )

        # Preview must match allocate_tranche / select_eligible (sector cap included).
        shortfall = max(0, int(target_n) - int(cutoff_opt.eligible_count))
        preview_cfg = ctx.cfg.model_copy(
            update={
                "scoring": ctx.cfg.scoring.model_copy(
                    update={"score_cutoff": cutoff_opt.cutoff}
                ),
                "sizing": ctx.cfg.sizing.model_copy(update={"target_names": int(target_n)}),
            }
        )
        preview_scores = [
            NameScore(
                ticker=row.ticker,
                name=row.name,
                factors={},
                total_score=float(row.total_score),
                eligibility=True,
                weight_input=float(row.total_score),
                eligibility_reason="preview",
                sector=str(getattr(row, "sector", "") or ""),
            )
            for row in ctx.scoreboard_rows
            if row.total_score is not None
            and float(row.total_score) >= float(cutoff_opt.cutoff)
        ]
        preview_alloc = allocate_tranche(
            preview_cfg,
            tranche_id=TrancheId.T1,
            scores=preview_scores,
            existing_weights={},
            tranche_budget=1.0,
        )
        preview = [
            (a.ticker, next((s.name for s in preview_scores if s.ticker == a.ticker), a.ticker), a.weight_input)
            for a in preview_alloc.allocated
            if a.incremental_weight > 0
        ]
        selected_n = len(preview)
        sector_shortfall = max(0, int(target_n) - selected_n)
        st.markdown(
            f"- 제안 북 예상: **{selected_n}종**"
            + (
                f" (적격 부족 shortfall={shortfall})"
                if shortfall
                else (
                    f" (섹터 캡 shortfall={sector_shortfall})"
                    if sector_shortfall
                    else ""
                )
            )
        )
        if preview:
            st.caption(
                "예상 편입(섹터 캡 반영): "
                + " · ".join(
                    f"{index}. {name or ticker}({ticker})({score:.2f})"
                    for index, (ticker, name, score) in enumerate(preview, 1)
                )
            )
        else:
            st.warning("이 절대 컷오프에서는 적격 종목이 0입니다.")

        changed = (
            current_n != int(target_n)
            or current_cutoff is None
            or abs(float(current_cutoff) - cutoff_opt.cutoff) > 1e-9
        )
        if not changed:
            st.success("현재 설정과 동일합니다.")
            return

        confirm_1 = st.checkbox(
            "절대 컷오프와 경계 종목을 확인했습니다",
            key="portfolio_abs_cutoff_confirm_1",
        )
        confirm_2 = st.checkbox(
            "확정 시 score_cutoff·target_names가 바뀌고 제안 북이 재계산됨을 이해했습니다 "
            "(target_portfolio.csv는 변경되지 않음)",
            key="portfolio_abs_cutoff_confirm_2",
        )
        if st.button(
            "절대 컷오프·편입 수 최종 확정",
            type="primary",
            disabled=not (confirm_1 and confirm_2),
            use_container_width=True,
            key="portfolio_abs_cutoff_save",
        ):
            try:
                backup = confirm_score_cutoff(
                    config_path=(
                        ctx.root / "alpha_system" / "config" / "alpha_system.yaml"
                    ),
                    cecs_path=(
                        ctx.root / "data" / "cecs_manual_scoring_template.csv"
                    ),
                    cutoff=cutoff_opt.cutoff,
                    confirm_understood=confirm_1,
                    confirm_final=confirm_2,
                    as_of=ctx.as_of or _date.today(),
                    journal_path=ctx.root / "data" / "alpha_system_journal.jsonl",
                    eligible_count=cutoff_opt.eligible_count,
                    rank_n=cutoff_opt.rank_n,
                    method="absolute_cutoff_then_count",
                    target_names=int(target_n),
                )
            except Exception as exc:
                st.error(str(exc))
            else:
                st.success(
                    f"cutoff {cutoff_opt.cutoff:.2f} / {int(target_n)}종 확정 · "
                    f"백업 `{backup.name}`"
                )
                st.rerun()
