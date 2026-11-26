"""Portfolio page — observation 30, proposal book, ops holdings."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date as _date
from pathlib import Path
from typing import Any

import html
import pandas as pd
import streamlit as st

from alpha_system.schema import TrancheId
from alpha_system.scoring.engine import NameScore
from alpha_system.sizing.allocate import allocate_tranche
from alpha_system.sizing.qual_overlay import (
    apply_evidence_withdrawn_gates,
    apply_opendart_flag_gates,
    journal_overlay_change,
    load_qual_overlay,
    overlay_path,
    save_qual_overlay,
)
from alpha_system.sizing.target_gate import collect_above_justified_target_tickers_from_root
from alpha_system.ui.services.context import DashboardContext, PortfolioRow
from alpha_system.ui.services.cecs_workbench import (
    build_relative_cutoff_ladder,
    confirm_score_cutoff,
    recommended_absolute_cutoff_option,
)
from alpha_system.ui.services.candidate_ai_export import build_candidate_ai_export
from alpha_system.ui.services.nav import consume_focus
from alpha_system.ui.services.portfolio_widgets import render_portfolio_bullets
from alpha_system.ui.services.rank_watchboard import (
    build_rank_watchboard,
    build_watch_table_rows,
    load_sector_labels,
    load_watch_metrics,
    naver_fchart_url,
    naver_name_chart_html,
    watch_tone_label,
)
from alpha_system.ui.services.sector_regime_fit import (
    build_sector_regime_board,
    fit_label_for_ticker,
    fit_why_for_ticker,
)

# 레짐 보완 후보 박스는 기회비용(주의·슬롯)만 키워 제거.
# 국면적합 열은 후보30 안에서만 Review 힌트로 유지.
from alpha_system.ui.services.approval_chrome import page_head, page_tabs
from alpha_system.ui.services.ui_copy import copy_get
from alpha_system.ui.services.screen_market import render_screen_market_nav
from alpha_system.screen_book import (
    is_kosdaq,
    save_kosdaq_policy,
    target_names_band,
    watch_max,
)
from alpha_system.ui.theme_prefs import watch_row_styles

try:
    from alpha_system.screen_book import is_short, save_short_policy
except ImportError:  # pragma: no cover — older screen_book without short horizon

    def is_short(horizon: object) -> bool:
        return str(horizon or "").strip().lower() in {"short", "단기", "st"}

    def save_short_policy(*_a, **_k):  # type: ignore[misc]
        return None


def _book_keys(ctx: DashboardContext) -> str:
    mkt = str(getattr(ctx, "screen_market", "KOSPI") or "KOSPI")
    hz = str(getattr(ctx, "screen_horizon", "mid") or "mid")
    return f"{mkt}_{hz}"


def _source_dir(ctx: DashboardContext):
    return getattr(ctx, "source_data_dir", None) or ctx.data_dir


def _watch_session_keys(ctx: DashboardContext) -> tuple[str, str, str]:
    tag = _book_keys(ctx)
    return f"pf_watch_{tag}", f"pf_watch_{tag}_sig", f"pf_watch_{tag}_last"


def _reset_watch_picker(ctx: DashboardContext, tickers: list[str]) -> None:
    key, _sig, last = _watch_session_keys(ctx)
    st.session_state.pop(key, None)
    st.session_state[last] = tuple(sorted(tickers))


def _watch_hold_flags(edited: object, *, n: int) -> list[bool]:
    """Read「보유」flags from data_editor frame (or arrow-fallback event)."""
    if n <= 0:
        return []
    # Native data_editor → DataFrame with 보유 column.
    try:
        import pandas as pd

        if isinstance(edited, pd.DataFrame) and "보유" in edited.columns:
            flags = [bool(v) for v in edited["보유"].tolist()[:n]]
            if len(flags) < n:
                flags.extend([False] * (n - len(flags)))
            return flags
    except Exception:  # noqa: BLE001 — fall through to selection event
        pass
    # HTML fallback may return DataframeFallbackEvent(selection.rows).
    rows = list(getattr(getattr(edited, "selection", None), "rows", None) or [])
    on = {int(i) for i in rows if 0 <= int(i) < n}
    return [i in on for i in range(n)]



def _pair_mid_short_ctx(
    ctx: DashboardContext,
) -> tuple[DashboardContext, DashboardContext]:
    """한 페이지에 중기+단기를 같이 쓰기 위해 짝 컨텍스트 로드."""
    from alpha_system.ui.services.context import load_context

    market = str(getattr(ctx, "screen_market", None) or "KOSPI")
    root = Path(ctx.root)
    if is_short(getattr(ctx, "screen_horizon", None)):
        short_ctx = ctx
        mid_ctx = load_context(root, market=market, horizon="mid")
    else:
        mid_ctx = ctx
        try:
            short_ctx = load_context(root, market=market, horizon="short")
        except Exception:  # noqa: BLE001
            short_ctx = ctx
    return mid_ctx, short_ctx


def _peer_market_mid_rows(
    root: Path,
    market: str,
    *,
    current_mid_rows: list[PortfolioRow] | None = None,
) -> tuple[list[PortfolioRow], list[PortfolioRow]]:
    """KOSPI/KOSDAQ mid Soft rows for combined budget strip (no ranking merge)."""
    from alpha_system.ui.services.context import load_context

    m = str(market or "KOSPI").strip().upper()
    cur = list(current_mid_rows or [])
    try:
        if m.startswith("KOSDAQ"):
            kosdaq = cur
            kospi = list(
                load_context(root, market="KOSPI", horizon="mid").portfolio_rows or []
            )
        else:
            kospi = cur
            kosdaq = list(
                load_context(root, market="KOSDAQ", horizon="mid").portfolio_rows or []
            )
    except Exception:  # noqa: BLE001
        if m.startswith("KOSDAQ"):
            return [], cur
        return cur, []
    return kospi, kosdaq


def _desk_records(
    ctx: DashboardContext,
    *,
    holdings_in_proposal_only: bool = False,
    sleeve: str = "중기",
) -> list[dict[str, object]]:
    """One decision row per name. Scores stay on 확인."""
    from alpha_system.ui.services.trade_desk import (
        ACTION_BUY,
        ACTION_CLEAR,
        ACTION_HOLD,
        ACTION_SELL,
        ACTION_TRIM,
        build_trade_desk,
        load_close_series,
        load_snapshot_prices,
    )

    proposal: list[tuple[str, str, float | None]] = []
    live: dict[str, float] = {}
    target_ok: dict[str, bool] = {}
    for row in list(ctx.portfolio_rows or []):
        tk = str(getattr(row, "ticker", "") or "").strip()
        if not tk:
            continue
        px = getattr(row, "current_price", None)
        try:
            price = float(px) if px is not None else None
        except (TypeError, ValueError):
            price = None
        proposal.append((tk, str(getattr(row, "name", "") or tk), price))
        nk = tk.zfill(6) if tk.isdigit() else tk
        if price is not None and price > 0:
            live[nk] = price
        tp = getattr(row, "target_price", None)
        try:
            tp_ok = float(tp) > 0 if tp is not None else False
        except (TypeError, ValueError):
            tp_ok = False
        target_ok[nk] = bool(getattr(row, "has_target", False)) and tp_ok
    holdings: list[tuple[str, str, float]] = []
    proposal_ids = {
        (t.zfill(6) if t.isdigit() else t) for t, _, _ in proposal
    }
    for row in _saved_kr_alpha_rows(ctx):
        tk = str(row["ticker"])
        if holdings_in_proposal_only and tk not in proposal_ids:
            continue
        holdings.append((tk, str(row["name"]), float(row["quantity"])))
    tickers = {
        (t.zfill(6) if t.isdigit() else t)
        for t, _, _ in proposal + holdings
    }
    closes = load_close_series(Path(ctx.root), tickers)
    live.update(load_snapshot_prices(Path(ctx.root), tickers))
    desk = build_trade_desk(
        proposal=proposal,
        holdings=holdings,
        closes_by_ticker=closes,
        live_price=live,
    )
    weights = _proposal_weight_by_ticker(ctx)
    mid_soft = str(sleeve).startswith("중기")
    soft_hints: dict[str, Any] = {}
    if mid_soft:
        try:
            from alpha_system.proposal_chart import norm_ticker
            from alpha_system.ui.services.alpha_book_ops import (
                load_alpha_book_ops,
                today_buy_names_max,
            )
            from alpha_system.ui.services.soft_trade_priority import (
                hints_by_ticker,
                rank_soft_trade_hints,
            )

            held_set = {
                tk
                for t, _, _ in holdings
                if (tk := norm_ticker(t))
            }
            today_n = int(
                today_buy_names_max(policy=load_alpha_book_ops(Path(ctx.root)))
            )
            soft_hints = hints_by_ticker(
                rank_soft_trade_hints(
                    list(ctx.portfolio_rows or []),
                    held=held_set,
                    today_buy_max=today_n,
                )
            )
        except Exception:  # noqa: BLE001
            soft_hints = {}

    action_ord = {
        ACTION_SELL: 0,
        ACTION_TRIM: 1,
        ACTION_CLEAR: 2,
        ACTION_HOLD: 3,
        ACTION_BUY: 4,
        "보류": 5,
    }
    out: list[dict[str, object]] = []
    for row in desk:
        weight = weights.get(row.ticker)
        action = row.action
        signal = row.signal
        human = ""
        pri: int | None = None
        if mid_soft and action == ACTION_BUY:
            from alpha_system.proposal_chart import norm_ticker as _nt

            hint = soft_hints.get(_nt(row.ticker) or row.ticker)
            if hint is None:
                hint = soft_hints.get(row.ticker)
            if hint is not None:
                pri = int(hint.rank)
                human = hint.human_ko
                signal = hint.human_ko
                if hint.stance in ("보류", "패스") or not hint.today_slot:
                    action = "보류"
                else:
                    action = ACTION_BUY
            elif not target_ok.get(row.ticker, False):
                action = "보류"
                signal = "목표가 없음 · 사기 금지"
                human = signal
            else:
                human = "미정 · 살지/보류/패스"
        elif mid_soft and action == ACTION_HOLD:
            human = "보유 · 배지·월 Review"
        elif mid_soft and action in (ACTION_SELL, ACTION_TRIM, ACTION_CLEAR):
            human = "배지만 집행 · Soft 순위 추종 금지"
        elif not mid_soft:
            human = "단기 · Soft와 섞지 않음"
        out.append(
            {
                "우선": pri,
                "할 일": action,
                "구분": sleeve,
                "종목": row.name,
                "코드": row.ticker,
                "보유": row.held,
                "제안": row.proposal,
                "비중": round(weight, 1) if weight is not None else None,
                "현재가": row.price,
                "신호": signal,
                "사람": human or "—",
            }
        )
    out.sort(
        key=lambda r: (
            action_ord.get(str(r.get("할 일") or ""), 50),
            int(r["우선"]) if isinstance(r.get("우선"), int) else 999,
            str(r.get("종목") or ""),
        )
    )
    return out


def _render_trade_desk(
    ctx: DashboardContext, *, holdings_in_proposal_only: bool = False
) -> None:
    """Single-sleeve desk. The page uses _render_today_book so a name appears once."""
    rows = _desk_records(
        ctx,
        holdings_in_proposal_only=holdings_in_proposal_only,
    )
    if not rows:
        st.info("이 장부에 제안·보유가 없습니다.")
        return
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _activist_desk_records(ctx: DashboardContext) -> list[dict[str, object]]:
    """행동주의 Review 제안·보유 → 오늘 매매 행 (Soft와 이원)."""
    if is_short(getattr(ctx, "screen_horizon", None)):
        return []
    root = Path(getattr(ctx, "root", ".") or ".")
    mkt = str(getattr(ctx, "screen_market", None) or "KOSPI")
    try:
        from alpha_system.review.treasury_activist_proposal import (
            build_activist_proposal,
            load_activist_held_tickers,
        )
        from alpha_system.ui.services.alpha_book_ops import (
            activist_today_buy_names_max,
            load_alpha_book_ops,
        )
        from alpha_system.ui.services.trade_desk import (
            ACTION_BUY,
            ACTION_HOLD,
            ACTION_SELL,
            load_snapshot_prices,
        )

        from alpha_system.proposal_chart import norm_ticker as _norm_tk

        soft_tks = [
            tk
            for r in (ctx.portfolio_rows or [])
            if (tk := _norm_tk(getattr(r, "ticker", None)))
        ]
        pol = load_alpha_book_ops(root)
        board = build_activist_proposal(
            root,
            market=mkt,
            soft_tickers=soft_tks,
            today_buy_names_max=int(activist_today_buy_names_max(policy=pol)),
        )
        held = {
            tk
            for raw in load_activist_held_tickers(
                root, positions_path=Path(ctx.data_dir) / "positions.csv"
            )
            if (tk := _norm_tk(raw))
        }
    except Exception:  # noqa: BLE001
        return []

    from alpha_system.proposal_chart import norm_ticker as _norm_tk
    from alpha_system.ui.services.soft_trade_priority import (
        activist_human_default,
    )

    prop_by = {_norm_tk(r.ticker) or r.ticker: r for r in board.rows}
    # 승격·제안 순서 우선 · 보유만 있는 종목은 뒤
    ordered: list[str] = []
    seen_tk: set[str] = set()
    for r in board.rows:
        tk = _norm_tk(r.ticker) or r.ticker
        if tk and tk not in seen_tk:
            ordered.append(tk)
            seen_tk.add(tk)
    for tk in sorted(held):
        if tk not in seen_tk:
            ordered.append(tk)
            seen_tk.add(tk)
    if not ordered:
        return []
    live = load_snapshot_prices(root, set(ordered))
    today_a = int(activist_today_buy_names_max(policy=pol))
    buy_new = [tk for tk in ordered if tk in prop_by and tk not in held]
    buy_rank = {tk: i for i, tk in enumerate(buy_new, start=1)}
    out: list[dict[str, object]] = []
    for tk in ordered:
        row = prop_by.get(tk)
        name = str(getattr(row, "name", None) or tk) if row else tk
        in_prop = tk in prop_by
        in_held = tk in held
        if in_prop and in_held:
            action = ACTION_HOLD
            human = "보유 · Soft와 합산 금지"
            pri: int | None = None
        elif in_prop:
            rank = buy_rank.get(tk)
            if rank is not None and rank <= today_a:
                action = ACTION_BUY
                human = activist_human_default(
                    today_rank=rank, today_max=today_a
                )
                pri = rank
            else:
                action = "보류"
                human = activist_human_default(today_rank=None, today_max=today_a)
                pri = rank
        else:
            action = ACTION_SELL
            human = "촉매 종료 Review · Soft와 합산 금지"
            pri = None
        w = float(getattr(row, "of_mid_soft_pct", 0) or 0) if row else None
        out.append(
            {
                "우선": pri,
                "할 일": action,
                "구분": "행동주의",
                "종목": name,
                "코드": tk,
                "보유": "Y" if in_held else "",
                "제안": "Y" if in_prop else "",
                "비중": round(w, 2) if w is not None else None,
                "현재가": live.get(tk),
                "신호": (
                    f"Soft대비 {w:g}%"
                    if w is not None
                    else "보유만 · 촉매 Review"
                ),
                "사람": human,
            }
        )
    return out


def _render_dual_sleeve_caption(ctx: DashboardContext) -> None:
    """Soft 75 · 행동주의 25 한 줄 (포트 집행 안내)."""
    root = Path(getattr(ctx, "root", ".") or ".")
    theme_pct = 25.0
    soft_n = len(ctx.portfolio_rows or [])
    act_n = 0
    try:
        from alpha_system.review.treasury_activist_proposal import (
            build_activist_proposal,
        )
        from alpha_system.review.treasury_activist_sizing import load_sizing_raw

        raw = load_sizing_raw(root)
        theme_pct = float(raw.get("theme_of_mid_soft_pct") or 50)
        soft_tks = [
            str(getattr(r, "ticker", "") or "").zfill(6)
            for r in (ctx.portfolio_rows or [])
            if str(getattr(r, "ticker", "") or "").strip("0")
        ]
        act_n = len(
            build_activist_proposal(
                root,
                market=str(getattr(ctx, "screen_market", None) or "KOSPI"),
                soft_tickers=soft_tks,
            ).rows
        )
    except Exception:  # noqa: BLE001
        pass
    soft_pct = max(0.0, 100.0 - theme_pct)
    st.markdown(
        f'<div class="pf-hh-tip" role="note">'
        f"<b>중기 반반</b> · 팩터 Soft ≈{soft_pct:g}% ({soft_n}종) · "
        f"하케다카 ≈{theme_pct:g}% ({act_n}종) · "
        f"겹치면 Soft 우선 · 합산 주문 금지 · HTS Review"
        f"</div>",
        unsafe_allow_html=True,
    )


def _desk_rows_tsv(rows: list[dict[str, object]]) -> str:
    """오늘 매매 행 → 탭 구분 텍스트 (표 칸 복사가 막힐 때 HTS 메모용)."""
    if not rows:
        return ""
    cols = list(rows[0].keys())
    lines = ["\t".join(cols)]
    for row in rows:
        lines.append(
            "\t".join(
                "" if row.get(c) is None else str(row.get(c)) for c in cols
            )
        )
    return "\n".join(lines)


def _desk_rows_csv_bytes(rows: list[dict[str, object]]) -> bytes:
    """오늘 매매 행 → UTF-8 BOM CSV (엑셀·메모장)."""
    import csv
    import io

    buf = io.StringIO()
    if not rows:
        return buf.getvalue().encode("utf-8-sig")
    cols = list(rows[0].keys())
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {c: ("" if row.get(c) is None else row.get(c)) for c in cols}
        )
    return buf.getvalue().encode("utf-8-sig")


def _render_today_book_copy(rows: list[dict[str, object]]) -> None:
    """st.dataframe은 칸 드래그 복사가 잘 안 됨 → TSV·CSV 병행."""
    with st.expander("표 복사 · HTS 메모용", expanded=False):
        st.caption(
            "위 표는 Streamlit 표라 칸을 드래그해 복사하기 어렵습니다. "
            "아래 텍스트를 드래그하거나 CSV를 받으세요."
        )
        st.code(_desk_rows_tsv(rows), language=None)
        st.download_button(
            "오늘 매매 CSV",
            data=_desk_rows_csv_bytes(rows),
            file_name="today_trades.csv",
            mime="text/csv",
            key="pf_today_book_csv",
        )


def _render_today_book(
    mid_ctx: DashboardContext, short_ctx: DashboardContext
) -> None:
    """중기 Soft·행동주의·단기 할 일을 종목당 한 줄로 합친다."""
    rows = _desk_records(mid_ctx, sleeve="중기 Soft")
    seen = {str(row["코드"]) for row in rows}
    for row in _activist_desk_records(mid_ctx):
        code = str(row["코드"])
        if code in seen:
            # Soft 우선: 행동주의 행은 Soft에 있으면 스킵
            continue
        rows.append(row)
        seen.add(code)
    for row in _desk_records(
        short_ctx, holdings_in_proposal_only=True, sleeve="단기"
    ):
        code = str(row["코드"])
        if code in seen:
            for kept in rows:
                if str(kept["코드"]) == code and str(kept["구분"]).startswith(
                    "중기"
                ):
                    kept["구분"] = f"{kept['구분']}·단기"
            continue
        rows.append(row)
        seen.add(code)
    st.markdown("**오늘 매매**")
    _render_dual_sleeve_caption(mid_ctx)
    st.caption(
        "주문은 HTS. 우선·사람=객관 기본안(Review). "
        "구분=중기 Soft / 행동주의 / 단기. "
        "Soft 오늘 신규≤2 · 행동주의≤1 · Soft와 합산 금지 · "
        "팔기=전량 · 줄이기=25% 또는 절반 · "
        "비중=Soft는 제안% · 행동주의는 Soft대비%."
    )
    if not rows:
        st.info(
            "Soft·행동주의 제안·보유가 없습니다. "
            "전략›승격 또는 아래에서 보유를 고르세요."
        )
        return
    st.dataframe(rows, use_container_width=True, hide_index=True)
    _render_today_book_copy(rows)
    act_html = _activist_ops_block_html(mid_ctx)
    if act_html:
        st.markdown(act_html, unsafe_allow_html=True)


def _candidate_edit_order(
    ctx: DashboardContext,
) -> list[tuple[str, str, float | None]]:
    """Scored candidates, then any held name the scoreboard does not list."""
    ranked: list[tuple[float, str, str]] = []
    seen: set[str] = set()
    for row in list(ctx.scoreboard_rows or []):
        tk = str(getattr(row, "ticker", "") or "").strip()
        if tk.isdigit():
            tk = tk.zfill(6)
        if not tk or tk in seen:
            continue
        seen.add(tk)
        name = str(getattr(row, "name", "") or tk)
        score = getattr(row, "total_score", None)
        try:
            score_n = float(score) if score is not None else None
        except (TypeError, ValueError):
            score_n = None
        ranked.append((score_n if score_n is not None else -1.0, name, tk))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    out: list[tuple[str, str, float | None]] = [
        (tk, name, None if sort_score < 0 else sort_score)
        for sort_score, name, tk in ranked
    ]
    for row in _saved_kr_alpha_rows(ctx):
        tk = str(row["ticker"])
        if tk not in seen:
            out.append((tk, str(row["name"]), None))
    return out


_SPARK_BARS = 60


def _extend_closes_with_snapshot(
    closes: dict[str, list[tuple[str, float]]],
    as_of: dict[str, str],
    live: dict[str, float],
) -> dict[str, list[tuple[str, float]]]:
    """Append the snapshot close when it is newer than the replay path."""
    if not as_of:
        return closes
    out = {tk: list(rows) for tk, rows in closes.items()}
    for tk, px in live.items():
        stamp = as_of.get(tk) or ""
        rows = out.get(tk)
        if not stamp or not rows or px <= 0:
            continue
        if rows[-1][0] < stamp:
            rows.append((stamp, float(px)))
        elif rows[-1][0] == stamp:
            rows[-1] = (stamp, float(px))
    return out


def _sparkline(series: list[tuple[str, float]] | None) -> list[float] | None:
    """Last closes for the in-table line. None when there is no path to draw."""
    if not series or len(series) < 2:
        return None
    return [round(float(px), 2) for _, px in series[-_SPARK_BARS:]]


def _candidate_edit_records(
    ctx: DashboardContext,
    qty_by: dict[str, float],
    closes: dict[str, list[tuple[str, float]]] | None = None,
) -> list[dict[str, object]]:
    """Candidate rows with the fields used to judge a hold."""
    from alpha_system.ui.services.rank_watchboard import (
        load_sector_labels,
        load_watch_metrics,
    )

    metrics = load_watch_metrics(ctx.root, data_dir=_source_dir(ctx))
    sectors = load_sector_labels(Path(ctx.root))
    weights = _proposal_weight_by_ticker(ctx)
    by_score: dict[str, object] = {}
    for row in list(ctx.scoreboard_rows or []):
        tk = str(getattr(row, "ticker", "") or "").strip()
        if tk.isdigit():
            tk = tk.zfill(6)
        if tk:
            by_score[tk] = row
    records: list[dict[str, object]] = []
    for tk, name, score in _candidate_edit_order(ctx):
        row = by_score.get(tk)
        slot = metrics.get(tk) or {}
        price = slot.get("price")
        target = slot.get("target")
        upside = None
        if price and target and float(price) > 0:
            upside = (float(target) - float(price)) / float(price) * 100
        eligible = getattr(row, "eligibility", None) if row is not None else None
        if eligible is True:
            elig = "예"
        elif eligible is False:
            elig = "아니오"
        else:
            elig = "—"
        weight = weights.get(tk)
        records.append(
            {
                "보유": tk in qty_by,
                "종목": name,
                "코드": tk,
                "일봉": _sparkline((closes or {}).get(tk)),
                "차트": naver_fchart_url(tk),
                "제안": "예" if weight is not None else "—",
                "비중": round(weight, 1) if weight is not None else None,
                "합계": score,
                "품질": getattr(row, "score_q", None) if row is not None else None,
                "가치": getattr(row, "score_v", None) if row is not None else None,
                "환원": getattr(row, "score_sr", None) if row is not None else None,
                "적격": elig,
                "섹터": sectors.get(tk) or (getattr(row, "sector", "") if row is not None else "") or "—",
                "PER": slot.get("per"),
                "PBR": slot.get("pbr"),
                "ROE": slot.get("roe"),
                "배당%": slot.get("dividend_yield"),
                "현재가": price,
                "목표가": target,
                "여유%": round(upside, 1) if upside is not None else None,
                "수량": qty_by.get(tk, 0.0),
            }
        )
    return records


def _render_editor_chart(
    order_rows: list[tuple[str, str, float | None]],
    qty_by: dict[str, float],
    closes: dict[str, list[tuple[str, float]]],
    *,
    pick_key: str,
) -> None:
    """One daily chart for the name chosen under the editor."""
    if not order_rows:
        return
    order = [tk for tk, _name, _score in order_rows]
    names = {tk: name for tk, name, _score in order_rows}
    if st.session_state.get(pick_key) not in order:
        st.session_state.pop(pick_key, None)
    held = [tk for tk in order if tk in qty_by]
    default_tk = held[0] if held else order[0]
    picked = st.selectbox(
        "일봉",
        order,
        index=order.index(default_tk),
        format_func=lambda tk: f"{names.get(tk, tk)} {tk}",
        key=pick_key,
    )
    series = closes.get(str(picked)) or []
    label = names.get(str(picked), str(picked))
    if len(series) < 2:
        st.caption(f"{label} 로컬 일봉이 없습니다. 표의 차트에서 네이버 일봉을 여세요.")
        return
    frame = pd.DataFrame(series, columns=["날짜", "종가"])
    close = frame["종가"]
    frame["20일"] = close.rolling(20).mean()
    frame["60일"] = close.rolling(60).mean()
    frame["120일"] = close.rolling(120).mean()
    last = float(close.iloc[-1])
    note = f"{label} 종가 {last:,.0f}"
    sma60 = frame["60일"].iloc[-1]
    sma120 = frame["120일"].iloc[-1]
    if pd.notna(sma60):
        side = "위" if last >= float(sma60) else "아래"
        note += f" · 60일선 {side}"
    if pd.notna(sma120):
        side = "위" if last >= float(sma120) else "아래"
        note += f" · 120일선 {side}"
    st.caption(note + ". 60일선 아래는 신규를 보류하고, 120일선 아래는 보유를 줄이는 쪽을 봅니다.")
    long = frame.melt(id_vars="날짜", var_name="선", value_name="가격").dropna()
    import altair as alt

    chart = (
        alt.Chart(long)
        .mark_line()
        .encode(
            x=alt.X("날짜:T", title=None),
            y=alt.Y("가격:Q", title=None, scale=alt.Scale(zero=False)),
            color=alt.Color(
                "선:N",
                sort=["종가", "20일", "60일", "120일"],
                legend=alt.Legend(title=None, orient="bottom"),
            ),
        )
        .properties(height=260)
    )
    st.altair_chart(chart, width="stretch")


def _render_book_editor(ctx: DashboardContext) -> None:
    """Pick holdings from the scored candidate list, not only today's trade rows."""
    from alpha_system.ui.services.trade_desk import (
        load_dated_closes,
        load_snapshot_closes,
    )

    saved = _saved_kr_alpha_rows(ctx)
    qty_by = {str(row["ticker"]): float(row["quantity"]) for row in saved}
    order_rows = _candidate_edit_order(ctx)
    order = [tk for tk, _name, _score in order_rows]
    root = Path(ctx.root)
    as_of, live = load_snapshot_closes(root, set(order))
    closes = _extend_closes_with_snapshot(
        load_dated_closes(root, set(order)), as_of, live
    )
    st.markdown("**보유 편집**")
    st.caption(
        f"후보 {len(order)}종. 일봉은 최근 {_SPARK_BARS}거래일, 차트는 네이버 일봉. "
        "합계·품질·가치·환원, PER·목표가 여유와 같이 보유를 고릅니다. 주문은 하지 않습니다."
    )
    if order:
        _render_editor_chart(
            order_rows,
            qty_by,
            closes,
            pick_key=f"book_edit_chart_pick_{_book_keys(ctx)}",
        )
        frame = pd.DataFrame(_candidate_edit_records(ctx, qty_by, closes))
        key = f"book_edit_px_{_book_keys(ctx)}"
        last = f"{key}_last"
        sig_key = f"{key}_sig"
        sig = tuple(order)
        if st.session_state.get(sig_key) != sig:
            st.session_state.pop(key, None)
            st.session_state[sig_key] = sig
            st.session_state[last] = tuple(sorted(qty_by))
        locked = [c for c in frame.columns if c != "보유"]
        edited = st.data_editor(
            frame,
            hide_index=True,
            width="stretch",
            height=480,
            row_height=36,
            disabled=locked,
            column_config={
                "보유": st.column_config.CheckboxColumn(
                    "보유",
                    help="체크하면 보유 장부에 넣고, 끄면 뺍니다.",
                    default=False,
                ),
                "일봉": st.column_config.LineChartColumn(
                    "일봉",
                    width="medium",
                    help=f"로컬 일봉 최근 {_SPARK_BARS}거래일. 칸마다 세로축이 따로입니다.",
                ),
                "차트": st.column_config.LinkColumn(
                    "차트",
                    help="네이버 일봉",
                    display_text="차트",
                    width="small",
                ),
                "비중": st.column_config.NumberColumn("비중", format="%.1f"),
                "합계": st.column_config.NumberColumn("합계", format="%.1f"),
                "품질": st.column_config.NumberColumn("품질", format="%.1f"),
                "가치": st.column_config.NumberColumn("가치", format="%.1f"),
                "환원": st.column_config.NumberColumn("환원", format="%.1f"),
                "PER": st.column_config.NumberColumn("PER", format="%.1f"),
                "PBR": st.column_config.NumberColumn("PBR", format="%.2f"),
                "ROE": st.column_config.NumberColumn("ROE", format="%.1f"),
                "배당%": st.column_config.NumberColumn("배당%", format="%.2f"),
                "현재가": st.column_config.NumberColumn("현재가", format="%.0f"),
                "목표가": st.column_config.NumberColumn("목표가", format="%.0f"),
                "여유%": st.column_config.NumberColumn(
                    "여유%",
                    format="%.1f",
                    help="목표가 대비 현재가 여유. 음수면 현재가가 목표가 위입니다.",
                ),
                "수량": st.column_config.NumberColumn("수량", format="%.0f"),
            },
            key=key,
        )
        flags = _watch_hold_flags(edited, n=len(order))
        chosen = [tk for tk, on in zip(order, flags) if on]
        current = tuple(sorted(chosen))
        prev = st.session_state.get(last)
        if prev is None:
            st.session_state[last] = tuple(sorted(qty_by))
        elif current != prev:
            _persist_watch_holdings(ctx, list(current))
            st.session_state[last] = current
            st.session_state.pop(key, None)
            st.rerun()
    _render_holdings_paste(ctx)


def render_portfolio(
    ctx: DashboardContext,
    *,
    proposal_eligible_sorter: Callable[
        [list[PortfolioRow], DashboardContext], list[PortfolioRow]
    ]
    | None = None,
    proposal_final_sort_label: str | None = None,
) -> None:
    consume_focus()  # confirmation CTAs land here; portfolio section tabs below
    if "holdings_input_open" not in st.session_state:
        st.session_state["holdings_input_open"] = True

    page_head(
        kicker=copy_get("portfolio", "page_kicker", default="포트폴리오"),
        title=copy_get(
            "portfolio", "page_title", default="알파 위성 · 오늘 매매"
        ),
        lead=copy_get(
            "portfolio",
            "page_lead",
            default=(
                "오늘 매매=중기 Soft + 행동주의 이원 집행 · "
                "후보·승격·해부는 왼쪽「전략 운용」· 주문은 사람·HTS."
            ),
        ),
    )
    render_screen_market_nav(ctx.root)
    st.caption(
        copy_get(
            "portfolio",
            "exec_only_caption",
            default=(
                "여기=집행만 · Soft 슬롯·대기·비율·순환=전략›중기 Soft 운영 데스크 · "
                "승격·시드%=전략›자사주·행동주의 · 해부=박홍기"
            ),
        )
    )

    mid_ctx, short_ctx = _pair_mid_short_ctx(ctx)
    if not (mid_ctx.scoreboard_rows or []) and not (short_ctx.scoreboard_rows or []):
        _render_status_card(
            "이 시장 정량이 없습니다. 확인 → ① 중기·단기 정량·정성 한 번에.",
            tone="warn",
        )

    tab_ops = copy_get("portfolio", "tab_ops", default="오늘 매매")
    tab_universe = copy_get("portfolio", "tab_universe", default="유니버스")
    # 테마·해부는 전략 운용 탭으로 이전 · 포트는 집행·유니버스만
    _pf_tabs = {tab_ops, tab_universe}
    if st.session_state.get("portfolio_section") not in _pf_tabs:
        # 예전「자사주·행동주의」탭 세션값 → 오늘 매매로
        st.session_state["portfolio_section"] = tab_ops
    if st.session_state.get("_pf_land_trade") != 1:
        st.session_state["portfolio_section"] = tab_ops
        st.session_state["_pf_land_trade"] = 1
    section = page_tabs(
        copy_get("portfolio", "tab_label", default="포트 보기"),
        (tab_ops, tab_universe),
        key="portfolio_section",
    )
    if section == tab_universe:
        from alpha_system.ui.services.portfolio_universe_board import (
            render_portfolio_universe_tab,
        )

        st.caption(
            copy_get(
                "portfolio",
                "universe_hub_caption",
                default=(
                    "한눈 참고 · Soft 운영 데스크=전략›중기 Soft · "
                    "테마=자사주·행동주의 · 해부=박홍기"
                ),
            )
        )
        render_portfolio_universe_tab(
            mid_ctx, short_ctx, root=Path(ctx.root)
        )
        return

    _render_today_book(mid_ctx, short_ctx)
    _render_book_editor(mid_ctx)
    if proposal_eligible_sorter is not None:
        _render_proposal_book(
            mid_ctx,
            proposal_eligible_sorter=proposal_eligible_sorter,
            proposal_final_sort_label=proposal_final_sort_label,
            section_kicker="중기",
        )
    st.markdown("**참고**")
    st.caption(
        "점수·제안 카드·보유 카드는 위 표에 합쳤습니다. "
        "여기는 태도와 예산만 보여 줍니다."
    )
    try:
        from alpha_system.ui.services.investment_stance import (
            investment_stance_html,
            load_investment_stance,
        )

        _stance = load_investment_stance(Path(ctx.root))
        _stance_html = investment_stance_html(_stance)
        if _stance_html:
            st.markdown(_stance_html, unsafe_allow_html=True)
    except Exception:  # noqa: BLE001
        pass

    # 가계 본체 vs 알파 위성 (목표바 위 · Review-only)
    try:
        from alpha_system.ui.services.alpha_envelope_board import (
            household_satellite_html,
            resolve_unified_sleeves,
        )

        _hh_sleeves = resolve_unified_sleeves(Path(ctx.root))
        st.markdown(
            household_satellite_html(
                mid_of_equity=float(getattr(_hh_sleeves, "mid_of_equity", 0.9)),
                short_of_equity=float(getattr(_hh_sleeves, "short_of_equity", 0.1)),
            ),
            unsafe_allow_html=True,
        )
        st.caption(
            copy_get(
                "portfolio",
                "household_satellite_caption",
                default=(
                    "가계 대부분=본체(앱 밖) · 여기 Soft+행동주의 위성 · "
                    "합산 집행·전량 알파 금지 · target 사람만"
                ),
            )
        )
    except Exception:  # noqa: BLE001
        pass

    # ② 목표 구성 바 (시장 70/30 통합 바는 접기 — 중복 완화)
    try:
        from alpha_system.ui.services.alpha_envelope_board import (
            book_slide_bar_html,
            build_book_slide_segments,
            combined_soft_budget_html,
            market_budget_frac_pct,
        )

        _segs, _sleeves = build_book_slide_segments(
            None,
            root=Path(ctx.root),
            mid_proposal_rows=list(mid_ctx.portfolio_rows or []),
            short_proposal_rows=list(short_ctx.portfolio_rows or []),
        )
        st.markdown(
            book_slide_bar_html(_segs, sleeves=_sleeves),
            unsafe_allow_html=True,
        )
        _mkt = str(getattr(mid_ctx, "screen_market", None) or "KOSPI")
        _pct = market_budget_frac_pct(Path(ctx.root), _mkt, "mid")
        st.caption(
            copy_get(
                "portfolio",
                "market_budget_caption",
                default=(
                    "중기 예산 중 이 시장 {pct}% (코스피70/코스닥30) · "
                    "Soft등분 · 순위는 시장별 · target 불변"
                ),
                pct=f"{_pct:g}",
            )
        )
        with st.expander(
            copy_get(
                "portfolio",
                "combined_soft_fold",
                default="코스피·코스닥 Soft 비중 합산 (참고)",
            ),
            expanded=True,
        ):
            _k_rows, _q_rows = _peer_market_mid_rows(
                Path(ctx.root),
                _mkt,
                current_mid_rows=list(mid_ctx.portfolio_rows or []),
            )
            st.markdown(
                combined_soft_budget_html(
                    Path(ctx.root),
                    kospi_rows=_k_rows,
                    kosdaq_rows=_q_rows,
                    horizon="mid",
                ),
                unsafe_allow_html=True,
            )
    except Exception:  # noqa: BLE001
        pass

    st.caption(
        copy_get(
            "portfolio",
            "soft_boards_moved",
            default=(
                "Soft 슬롯·대기·매매비율·순환매 = 전략 › 중기 Soft 운영 데스크 · "
                "여기는 오늘 매매만"
            ),
        )
    )
    if st.button(
        "중기 Soft 운영 데스크",
        key="pf_goto_mid_soft_boards",
        use_container_width=True,
    ):
        from alpha_system.ui.services.strategy_ops_catalog import strategy_page_key
        from alpha_system.ui.services.nav import navigate

        navigate(strategy_page_key("mid_soft"))


def _verdict_counts(ctx: DashboardContext) -> tuple[int, int, int, int]:
    eligible = list(ctx.portfolio_rows or [])
    blocked = list(getattr(ctx, "proposal_blocked_rows", None) or [])
    held = list(getattr(ctx, "ops_portfolio_rows", None) or [])
    prop_tks = {str(getattr(r, "ticker", "") or "").zfill(6) for r in eligible}
    overlap = sum(
        1
        for r in held
        if str(getattr(r, "ticker", "") or "").zfill(6) in prop_tks
    )
    return len(eligible), len(blocked), len(held), overlap


def _row_short_name(row: object) -> str:
    name = str(getattr(row, "name", "") or "").strip()
    tk = str(getattr(row, "ticker", "") or "").zfill(6)
    if name:
        return name if len(name) <= 8 else name[:7] + "…"
    return tk


def _membership_sets(
    ctx: DashboardContext,
) -> tuple[list[str], list[str], list[str], dict[str, object]]:
    prop_rows = list(ctx.portfolio_rows or [])
    held_rows = list(getattr(ctx, "ops_portfolio_rows", None) or [])
    prop: dict[str, object] = {}
    for r in prop_rows:
        tk = str(getattr(r, "ticker", "") or "").zfill(6)
        if tk.strip("0"):
            prop[tk] = r
    held: dict[str, object] = {}
    for r in held_rows:
        tk = str(getattr(r, "ticker", "") or "").zfill(6)
        if tk.strip("0"):
            held[tk] = r
    both = sorted(set(prop) & set(held))
    prop_only = sorted(set(prop) - set(held))
    held_only = sorted(set(held) - set(prop))
    return both, prop_only, held_only, {**prop, **held}


def _above_target_set(ctx: DashboardContext) -> set[str]:
    raw = getattr(ctx, "above_target_tickers", None) or set()
    out: set[str] = set()
    for t in raw:
        tk = str(t or "").zfill(6)
        if tk.strip("0"):
            out.add(tk)
    return out


def _held_only_todo(
    tk: str,
    row: object,
    *,
    above: set[str],
) -> str:
    """Held-only action — Soft drop ≠ auto Exit."""
    kind = str(getattr(row, "ops_signal", "") or "")
    label = str(getattr(row, "ops_signal_label", "") or "")
    trim = getattr(row, "ops_trim_pct", None)
    if (
        tk in above
        or kind == "cash_half"
        or label.startswith(("Cash", "환금"))
    ):
        pct = int(trim) if trim is not None else 50
        return f"Cash Review · {pct}% (at target · not Exit)"
    if (
        kind == "invalid"
        or label in {"No data", "No target", "데이터없음", "목표없음"}
        or kind == "missing"
    ):
        return "Hold judgment · check data/target (do not force Sell)"
    if kind == "trim" or label.startswith(("Trim", "줄이기")):
        pct = int(trim) if trim is not None else 25
        return f"Trim Review · {pct}%"
    if kind == "exit_full" or label.startswith(("Exit", "전량")):
        return "Exit Review · check badge/reason"
    return "Check badge · by drop reason (Exit/Cash/Hold)"


def _blocked_soft_bucket(reason: str) -> str:
    """대기 사유 → data | soft | other."""
    r = str(reason or "")
    if any(
        k in r
        for k in (
            "일봉",
            "데이터 부족",
            "데이터 채운",
            "판정 보류",
            "120일선 부족",
            "60일선 데이터",
        )
    ):
        return "data"
    if any(
        k in r
        for k in (
            "Soft",
            "이평",
            "score_m",
            "60일선 아래",
            "120",
            "미달",
            "게이트",
            "하케다카",
            "목표가",
        )
    ):
        return "soft"
    return "other"


def _blocked_bucket_counts(ctx: DashboardContext) -> tuple[int, int, int]:
    """(data_n, soft_n, other_n) from proposal_blocked_rows."""
    data_n = soft_n = other_n = 0
    for r in list(getattr(ctx, "proposal_blocked_rows", None) or []):
        reason = ""
        extra = getattr(r, "extra", None) or {}
        if isinstance(extra, dict):
            reason = str(extra.get("ineligible_reason") or "")
        if not reason:
            reason = str(getattr(r, "target_detail", "") or "")
        b = _blocked_soft_bucket(reason)
        if b == "data":
            data_n += 1
        elif b == "soft":
            soft_n += 1
        else:
            other_n += 1
    return data_n, soft_n, other_n


def _names_join(keys: list[str], src: dict[str, object], *, limit: int = 3) -> str:
    if not keys:
        return "없음"
    bits = [_row_short_name(src[k]) for k in keys[:limit]]
    extra = len(keys) - limit
    if extra > 0:
        bits.append(f"외 {extra}")
    return " · ".join(bits)


def _verdict_todos(ctx: DashboardContext) -> list[str]:
    eligible = list(ctx.portfolio_rows or [])
    held = list(getattr(ctx, "ops_portfolio_rows", None) or [])
    act_n = {"exit_full": 0, "cash_half": 0, "trim": 0, "missing": 0}
    for r in held:
        kind = str(getattr(r, "ops_signal", "") or "")
        if kind in act_n:
            act_n[kind] += 1
    sell_n = len(_holdings_sell_actions(ctx)) if held else 0
    todos: list[str] = []
    if act_n["exit_full"]:
        todos.append(f"Exit Review {act_n['exit_full']}")
    if act_n["cash_half"]:
        todos.append(f"Cash Review {act_n['cash_half']}")
    if act_n["trim"]:
        todos.append(f"Trim Review {act_n['trim']}")
    if sell_n and sell_n > (
        act_n["exit_full"] + act_n["cash_half"] + act_n["trim"]
    ):
        todos.append(f"Sell size today {sell_n}")
    if act_n["missing"]:
        todos.append(f"No target {act_n['missing']}")
    if not eligible:
        todos.append("Proposal empty · check Soft/trend/candidates")
    return todos


def _economy_stance_line(root: Path) -> tuple[str, str]:
    """(태도 제목, 포트 한 줄). 실패 시 기본."""
    try:
        from alpha_system.economy_compass.stress_overlay import build_bubble_stress_board
        from alpha_system.economy_signal import load_cached_signal
        from alpha_system.ui.services.economy_playbook import stage_playbook

        cached = load_cached_signal(root)
        stress = build_bubble_stress_board(cached)
        stage = (
            stress.posture_stage
            if stress.posture_stage is not None
            else (None if cached is None else cached.stage)
        )
        book = stage_playbook(stage)
        title = book.title or "국면 참고"
        body = " · ".join(c.body for c in book.cards[:2]) if book.cards else ""
        if not body:
            body = "나침반에서 국면 확인 · 종목 주문은 이 포트에서"
        return title, body
    except Exception:  # noqa: BLE001
        return (
            "국면 참고",
            "경제 나침반 = 거시만 · 알파 매매·비중은 이 화면",
        )


def _ops_playbook_html(
    mid_ctx: DashboardContext,
    short_ctx: DashboardContext,
    *,
    root: Path | None = None,
) -> str:
    """Trade-today order + sleeve/compass role — portfolio top."""
    base = Path(root or getattr(mid_ctx, "root", ".") or ".")
    mkt = str(getattr(mid_ctx, "screen_market", None) or "KOSPI")
    both, prop_only, held_only, src = _membership_sets(mid_ctx)
    sell_todos = _verdict_todos(mid_ctx)
    short_todos = [
        f"Short·{t}" if not str(t).startswith(("Short", "단기")) else str(t)
        for t in _verdict_todos(short_ctx)
    ]
    stance_title, stance_body = _economy_stance_line(base)

    above = _above_target_set(mid_ctx)
    held_cash = [tk for tk in held_only if tk in above]
    held_exit = [tk for tk in held_only if tk not in above]
    sell_n = len(held_only) + sum(
        1
        for t in sell_todos
        if any(
            k in t
            for k in ("Exit", "Cash", "Trim", "Sell", "전량", "환금", "줄이기", "매도")
        )
    )
    if held_only:
        bits: list[str] = []
        if held_exit:
            bits.append(f"Exit review {_names_join(held_exit, src)}")
        if held_cash:
            bits.append(f"Cash (target) {_names_join(held_cash, src)}")
        sell_label = (
            " · ".join(bits) if bits else f"Held-only {_names_join(held_only, src)}"
        )
    else:
        sell_label = (
            "Signal " + " · ".join(sell_todos[:2]) if sell_todos else "No urgent sell"
        )
    hold_label = (
        f"{_names_join(both, src)} · check badge"
        if both
        else "None in both · register holdings first"
    )
    today_n = 2
    hold_lo, hold_hi = 4, 6
    try:
        from alpha_system.ui.services.alpha_book_ops import (
            load_alpha_book_ops,
            today_buy_names_max,
        )

        _pol = load_alpha_book_ops(base)
        today_n = int(today_buy_names_max(policy=_pol))
        hold_lo = int(_pol.funnel.hold_soft_min)
        hold_hi = int(_pol.funnel.hold_soft_max)
    except Exception:  # noqa: BLE001
        pass

    if prop_only:
        buy_label = (
            f"{_names_join(prop_only, src)} · 집행슬롯 오늘≤{today_n}종 "
            f"(제안 {len(prop_only)}≠전량매수) · 적합도% · 하루≤33%"
        )
    else:
        buy_label = "신규 슬롯 없음 · 미집행=단기채 파킹 (전량 단기채 아님)"

    steps = (
        f'<div class="pf-ops-step pf-ops-hold">'
        f'<div class="pf-ops-num">0</div>'
        f'<div class="pf-ops-body">'
        f'<div class="pf-ops-h">Ready to judge?</div>'
        f'<div class="pf-ops-d">Data as-of · open orders · same-day fills</div>'
        f'<div class="pf-ops-hint">'
        "보유체크=HTS 동기화 · Missing data ≠ Soft fail · Confirm 후 재조회"
        "</div>"
        f"</div></div>"
        f'<div class="pf-ops-step pf-ops-sell">'
        f'<div class="pf-ops-num">1</div>'
        f'<div class="pf-ops-body">'
        f'<div class="pf-ops-h">Sell first</div>'
        f'<div class="pf-ops-d">{_esc(sell_label)}</div>'
        f'<div class="pf-ops-hint">'
        "Badge final size only · strongest of Exit&gt;Cash&gt;Trim (no sum) · "
        "held-only at target = Cash · 보유만≠무조건 전량"
        "</div>"
        f"</div></div>"
        f'<div class="pf-ops-step pf-ops-hold">'
        f'<div class="pf-ops-num">2</div>'
        f'<div class="pf-ops-body">'
        f'<div class="pf-ops-h">Hold · both</div>'
        f'<div class="pf-ops-d">{_esc(hold_label)}</div>'
        f'<div class="pf-ops-hint">'
        f"Proposal∩held · 추매 적합도≥50% · Soft 보유 목표 {hold_lo}–{hold_hi}종 수렴"
        "</div>"
        f"</div></div>"
        f'<div class="pf-ops-step pf-ops-buy">'
        f'<div class="pf-ops-num">3</div>'
        f'<div class="pf-ops-body">'
        f'<div class="pf-ops-h">Buy · proposal only</div>'
        f'<div class="pf-ops-d">{_esc(buy_label)}</div>'
        f'<div class="pf-ops-hint">'
        f"오늘 신규 ≤{today_n}종 · 적합도%+하루≤33% · 관찰풀 매수 금지 · "
        "미집행=단기채 · HTS"
        "</div>"
        f"</div></div>"
    )

    detail_bits = sell_todos[:3] + short_todos[:2]
    if not detail_bits:
        detail_bits = ["No urgent action · review sets/cards below"]
    try:
        from alpha_system.ui.services.investment_stance import (
            load_investment_stance,
            stance_todos,
        )

        detail_bits = stance_todos(
            load_investment_stance(base), limit=3
        ) + detail_bits
    except Exception:  # noqa: BLE001
        pass
    gieop_line = _gieop_bridge_summary_line(mid_ctx)
    if gieop_line:
        detail_bits = [gieop_line] + detail_bits
    detail_html = "".join(
        f'<div class="pf-verdict-todo">{_esc(t)}</div>' for t in detail_bits
    )

    m_el, m_bl, m_he, m_ov = _verdict_counts(mid_ctx)
    s_el, _, s_he, _ = _verdict_counts(short_ctx)
    activist_html = _activist_ops_block_html(mid_ctx, root=base)

    return (
        '<div class="pf-verdict pf-ops-playbook" role="region" '
        'aria-label="Trade today ops">'
        '<div class="pf-verdict-kicker">Trade today · ops order</div>'
        f'<div class="pf-verdict-title">{_esc(mkt)} · Check → Sell → Hold → Buy</div>'
        '<div class="pf-verdict-scope">'
        f"깔때기: Soft 관찰→제안→오늘 신규≤{today_n}종→보유 Soft {hold_lo}–{hold_hi} 수렴 · "
        "행동주의=이원 블록 · Mix=target bar · Compass=거시만 · "
        "자동주문·target 없음 · 부분체결 후 재조회"
        "</div>"
        f'<div class="pf-ops-stance">'
        f'<span class="pf-ops-stance-k">Compass posture</span>'
        f'<span class="pf-ops-stance-t">{_esc(stance_title)}</span>'
        f'<span class="pf-ops-stance-b">{_esc(stance_body)}</span>'
        f"</div>"
        f'<div class="pf-ops-steps">{steps}</div>'
        f"{activist_html}"
        f'<div class="pf-verdict-grid">'
        f'<div class="pf-verdict-cell pf-verdict-ok">'
        f'<div class="pf-verdict-k">Mid proposal</div>'
        f'<div class="pf-verdict-n">{m_el}</div>'
        f'<div class="pf-verdict-s">Wait {m_bl} · Held {m_he} · Both {m_ov}</div></div>'
        f'<div class="pf-verdict-cell">'
        f'<div class="pf-verdict-k">Sell Review</div>'
        f'<div class="pf-verdict-n">{len(held_only)}</div>'
        f'<div class="pf-verdict-s">Held-only · signals {sell_n}</div></div>'
        f'<div class="pf-verdict-cell pf-verdict-ok">'
        f'<div class="pf-verdict-k">Buy Review</div>'
        f'<div class="pf-verdict-n">{len(prop_only)}</div>'
        f'<div class="pf-verdict-s">Short prop {s_el} · short held {s_he}</div></div>'
        f"</div>"
        f'<div class="pf-verdict-do">'
        f'<div class="pf-verdict-do-h">Signal notes</div>'
        f"{detail_html}"
        f"</div>"
        "</div>"
    )


def _gieop_bridge_summary_line(ctx: DashboardContext) -> str:
    """기업해부 심층 × Soft×보유 한 줄 · 보드 없으면 빈 문자열."""
    try:
        from alpha_system.proposal_chart import norm_ticker
        from alpha_system.ui.services.gieop_observe_board import (
            build_portfolio_bridge,
            load_observe_ui_board,
        )

        market = str(getattr(ctx, "screen_market", None) or "KOSPI")
        board = load_observe_ui_board(Path(ctx.root), market=market)
        if not board.available or not board.deep_pick:
            return ""
        soft = [
            norm_ticker(getattr(r, "ticker", None))
            for r in (ctx.portfolio_rows or [])
            if norm_ticker(getattr(r, "ticker", None))
        ]
        held = [
            norm_ticker(getattr(r, "ticker", None))
            for r in (getattr(ctx, "ops_portfolio_rows", None) or [])
            if norm_ticker(getattr(r, "ticker", None))
        ]
        bridge = build_portfolio_bridge(
            board.deep_pick, soft_tickers=soft, held_tickers=held
        )
        return bridge.summary_line_ko()
    except Exception:  # noqa: BLE001
        return ""


def _portfolio_verdict_html(ctx: DashboardContext) -> str:
    """단일 장부 결론(하위 호환·테스트)."""
    short = is_short(getattr(ctx, "screen_horizon", None))
    el, bl, he, ov = _verdict_counts(ctx)
    todos = _verdict_todos(ctx) or ["긴급 액션 없음 · 제안·보유만 Review"]
    book = "단기" if short else "중기"
    mkt = str(getattr(ctx, "screen_market", None) or "KOSPI")
    cells = (
        f'<div class="pf-verdict-cell pf-verdict-ok">'
        f'<div class="pf-verdict-k">최종 제안</div>'
        f'<div class="pf-verdict-n">{el}</div>'
        f'<div class="pf-verdict-s">편입 · 비중은 ③</div></div>'
        f'<div class="pf-verdict-cell pf-verdict-warn">'
        f'<div class="pf-verdict-k">대기</div>'
        f'<div class="pf-verdict-n">{bl}</div>'
        f'<div class="pf-verdict-s">편입하지 않음</div></div>'
        f'<div class="pf-verdict-cell">'
        f'<div class="pf-verdict-k">실보유</div>'
        f'<div class="pf-verdict-n">{he}</div>'
        f'<div class="pf-verdict-s">제안중 {ov}</div></div>'
    )
    todo_html = "".join(
        f'<div class="pf-verdict-todo">{_esc(t)}</div>' for t in todos[:4]
    )
    return (
        '<div class="pf-verdict">'
        '<div class="pf-verdict-kicker">결론 · 무엇을 넣고·빼고·들고 있나</div>'
        f'<div class="pf-verdict-title">{_esc(mkt)} · {_esc(book)}</div>'
        '<div class="pf-verdict-scope">'
        "③ 제안 · ④ 보유가 결정면 · 후보·컷은 아래 입력 · "
        "자동주문·target 기입 없음"
        "</div>"
        f'<div class="pf-verdict-grid">{cells}</div>'
        f'<div class="pf-verdict-do">'
        f'<div class="pf-verdict-do-h">오늘 Review</div>'
        f"{todo_html}"
        f"</div>"
        "</div>"
    )


def _portfolio_verdict_html_unified(
    mid_ctx: DashboardContext,
    short_ctx: DashboardContext,
) -> str:
    """하위 호환 — 통합 운영판과 동일 축."""
    return _ops_playbook_html(
        mid_ctx,
        short_ctx,
        root=Path(getattr(mid_ctx, "root", ".") or "."),
    )


def _fmt_num(val, *, integers: bool = False) -> str:
    if val is None:
        return "—"
    try:
        n = float(val)
    except (TypeError, ValueError):
        return "—"
    if integers:
        return f"{int(round(n)):,}"
    return f"{n:.2f}"


def _alpha_causal_strip_html(*, soft_n: int, held_n: int) -> str:
    """층별 인과 한눈 · Soft/target 불변 안내."""
    from html import escape as _e

    steps = (
        (
            "ctrl",
            "제어",
            copy_get(
                "portfolio",
                "causal_ctrl",
                default="확인① 정량 · 아래 관찰 파이프",
            ),
        ),
        (
            "exec",
            "L2 집행",
            copy_get(
                "portfolio",
                "causal_exec",
                default="Soft {n} → 오늘 매매·제안",
                n=int(soft_n),
            ),
        ),
        (
            "obs",
            "L3 관찰",
            copy_get(
                "portfolio",
                "causal_obs",
                default="가치·심층·해부 → 매수 아님·파킹",
            ),
        ),
        (
            "human",
            "L4 사람",
            copy_get(
                "portfolio",
                "causal_human",
                default="보유 {n} · target·HTS",
                n=int(held_n),
            ),
        ),
    )
    cards = "".join(
        f'<div class="pf-causal-card pf-causal-{_e(key)}">'
        f'<div class="pf-causal-k">{_e(title)}</div>'
        f'<div class="pf-causal-body">{_e(body)}</div>'
        f"</div>"
        for key, title, body in steps
    )
    return f'<div class="pf-causal" role="note">{cards}</div>'


def _run_observe_pipe(
    ctx: DashboardContext,
    *,
    market: str,
    soft_rows: list,
    soft_tks: list[str],
    held_tks: list[str],
) -> dict:
    """저PBR 갱신 → 알파 시드 → 정량커버 · Soft·target 불변."""
    from alpha_system.ui.services.gieop_observe_board import run_observe_pipe

    return run_observe_pipe(
        Path(ctx.root),
        market=market,
        soft_rows=soft_rows,
        soft_tickers=soft_tks,
        held_tickers=held_tks,
    )


def render_gieop_observe_desk(ctx: DashboardContext) -> None:
    """기업해부(박홍기) · 저PBR + 알파 후보 능동 평가 · Soft 불변."""
    from alpha_system.proposal_chart import norm_ticker
    from alpha_system.ui.services.gieop_alpha_seed import (
        alpha_seed_queue_html,
        collect_alpha_gieop_candidates,
        seed_alpha_to_gieop,
    )
    from alpha_system.ui.services.gieop_fusion_desk import (
        build_fusion_desk,
        fusion_status_html,
        refresh_quant_on_drafts,
    )
    from alpha_system.ui.services.gieop_observe_board import (
        build_portfolio_bridge,
        load_observe_ui_board,
        observe_board_html,
        open_path,
        portfolio_bridge_html,
        refresh_observe_board,
        resolve_gieop_paths,
    )
    from alpha_system.ui.services.gieop_today_loop import (
        build_today_gieop_loop,
        today_gieop_loop_html,
    )
    from alpha_system.review.essence_recommend import (
        build_essence_recommend,
        essence_recommend_html,
    )

    market = str(getattr(ctx, "screen_market", None) or "KOSPI")
    paths = resolve_gieop_paths(ctx.root)
    board = load_observe_ui_board(ctx.root, market=market)
    soft_rows = list(ctx.portfolio_rows or [])
    soft_tks = [
        norm_ticker(getattr(r, "ticker", None))
        for r in soft_rows
        if norm_ticker(getattr(r, "ticker", None))
    ]
    held_tks = [
        norm_ticker(getattr(r, "ticker", None))
        for r in (getattr(ctx, "ops_portfolio_rows", None) or [])
        if norm_ticker(getattr(r, "ticker", None))
    ]
    bridge = build_portfolio_bridge(
        board.deep_pick, soft_tickers=soft_tks, held_tickers=held_tks
    )
    alpha_board = collect_alpha_gieop_candidates(
        Path(ctx.root),
        market=market,
        soft_rows=soft_rows,
        held_tickers=held_tks,
        include_value_only=True,
        value_only_max=5,
    )
    fusion = build_fusion_desk(
        Path(ctx.root),
        market=market,
        candidates=alpha_board.candidates,
    )
    today = build_today_gieop_loop(
        market=market,
        fusion_rows=fusion.rows,
        bridge_rows=bridge.rows,
        deep_pick=board.deep_pick,
        candidates=alpha_board.candidates,
        max_picks=3,
    )
    deep_n = len(board.deep_pick)
    alpha_n = len(alpha_board.candidates)
    title = copy_get(
        "portfolio",
        "sec_gieop",
        default="오늘 해부 · 박홍기",
    )
    fold_bits = [title]
    if today.picks:
        fold_bits.append(
            " · ".join(f"{p.name}" for p in today.picks[:3])
        )
    elif deep_n or alpha_n:
        fold_bits.append("파이프 후 2~3종")
    else:
        fold_bits.append("파이프 먼저")
    with st.expander(" · ".join(fold_bits), expanded=True):
        st.markdown(
            _fold_lead_html(
                purpose=copy_get(
                    "portfolio",
                    "gieop_purpose",
                    default=(
                        "시총이 아니라 논리·퀄·Soft로 오늘 해부 2~3종을 고른다. "
                        "깊은 조사는 박홍기 · Soft·target 불변."
                    ),
                ),
                do_now=copy_get(
                    "portfolio",
                    "gieop_do_now",
                    default=(
                        "① 파이프 ② 본질 추천·오늘 카드 확인 ③ 박홍기 해부 "
                        "④ 할 일(사/유지/팔/대기) ⑤ Soft·HTS"
                    ),
                ),
                ignore="시총 컷 · 전 종목 해부 · Soft 자동편입 · target 자동 · 저P=매수",
            ),
            unsafe_allow_html=True,
        )
        chips: list[tuple[str, str]] = [("Review-only", "muted")]
        if today.picks:
            chips.append((f"오늘 {len(today.picks)}종", "warn"))
        if bridge.rows:
            chips.append((bridge.summary_line_ko().split(": ", 1)[-1], "muted"))
        if fusion.rows:
            chips.append(
                (
                    f"정량↑{fusion.n_quant_hi}",
                    "muted",
                )
            )
        _render_section_head(
            title,
            summary=copy_get(
                "portfolio",
                "gieop_caption",
                default="본질(논리·퀄·Soft) 2~3종 → 박홍기 → 할 일 · 시총 하한 없음",
            ),
            chips=chips,
            tier="review",
        )
        try:
            essence = build_essence_recommend(
                Path(ctx.root),
                market=market,
                soft_rows=soft_rows,
                pick_n=5,
            )
            st.markdown(essence_recommend_html(essence), unsafe_allow_html=True)
        except Exception:  # noqa: BLE001
            pass
        st.markdown(today_gieop_loop_html(today), unsafe_allow_html=True)
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            if st.button(
                copy_get(
                    "portfolio",
                    "gieop_btn_pipe",
                    default="① 관찰 파이프",
                ),
                key=f"gieop_pipe_{_book_keys(ctx)}",
                use_container_width=True,
                type="primary",
                help="저PBR→시드→정량커버 · Soft·target 불변",
            ):
                pipe = _run_observe_pipe(
                    ctx,
                    market=market,
                    soft_rows=soft_rows,
                    soft_tks=soft_tks,
                    held_tks=held_tks,
                )
                st.success(
                    copy_get(
                        "portfolio",
                        "gieop_pipe_ok",
                        default=(
                            "파이프 완료 · 시드 {n}/{s} · 정량 {q} "
                            "(↑{h}/中{m}/↓{l}) · 아래 카드 확인"
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
                copy_get(
                    "portfolio",
                    "gieop_btn_open",
                    default="② 박홍기 열기",
                ),
                key=f"gieop_open_{_book_keys(ctx)}",
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
                copy_get(
                    "portfolio", "gieop_btn_drafts", default="내조사 폴더"
                ),
                key=f"gieop_drafts_{_book_keys(ctx)}",
                use_container_width=True,
                disabled=not paths.drafts_ok,
            ):
                err = open_path(paths.drafts_dir)
                if err:
                    st.warning(err)
        _render_holdings_one_click(
            ctx,
            soft_tickers=soft_tks,
            deep_tickers=[
                norm_ticker(getattr(r, "ticker", None))
                for r in (board.deep_pick or [])
                if norm_ticker(getattr(r, "ticker", None))
            ],
            held_tickers=held_tks,
        )
        if not paths.start_ok:
            st.caption(
                copy_get(
                    "portfolio",
                    "gieop_missing",
                    default=(
                        f"시작하기.html 없음 · {paths.start_html} · "
                        "data/local/gieop_paths.json 에 gieop_root 지정"
                    ),
                )
            )
        with st.expander(
            copy_get(
                "portfolio",
                "gieop_detail_fold",
                default="상세 표 · 정량·큐·저P·포트연결 (평소 접기)",
            ),
            expanded=False,
        ):
            st.markdown(fusion_status_html(fusion), unsafe_allow_html=True)
            st.markdown(alpha_seed_queue_html(alpha_board), unsafe_allow_html=True)
            st.markdown(observe_board_html(board), unsafe_allow_html=True)
            st.markdown(portfolio_bridge_html(bridge), unsafe_allow_html=True)
        with st.expander(
            copy_get(
                "portfolio",
                "gieop_advanced_fold",
                default="고급 · 단계별 갱신 (평소 파이프만)",
            ),
            expanded=False,
        ):
            a1, a2, a3 = st.columns(3)
            with a1:
                if st.button(
                    copy_get(
                        "portfolio",
                        "gieop_btn_refresh",
                        default="저PBR만",
                    ),
                    key=f"gieop_refresh_{_book_keys(ctx)}",
                    use_container_width=True,
                ):
                    refresh_observe_board(
                        ctx.root,
                        market=market,
                        soft_tickers=soft_tks,
                        write_drafts=True,
                    )
                    st.success(
                        copy_get(
                            "portfolio",
                            "gieop_refresh_ok",
                            default="관찰 보드·기업해부 초안을 갱신했습니다.",
                        )
                    )
                    st.rerun()
            with a2:
                if st.button(
                    copy_get(
                        "portfolio",
                        "gieop_btn_alpha_seed",
                        default="시드만",
                    ),
                    key=f"gieop_alpha_seed_{_book_keys(ctx)}",
                    use_container_width=True,
                ):
                    seeded = seed_alpha_to_gieop(
                        Path(ctx.root),
                        market=market,
                        soft_rows=soft_rows,
                        held_tickers=held_tks,
                        include_value_only=True,
                        value_only_max=5,
                    )
                    st.success(
                        copy_get(
                            "portfolio",
                            "gieop_alpha_seed_ok",
                            default="알파 후보 초안 신규 {n} · skip {s}",
                            n=len(seeded.written),
                            s=len(seeded.skipped),
                        )
                    )
                    st.rerun()
            with a3:
                if st.button(
                    copy_get(
                        "portfolio",
                        "gieop_btn_quant",
                        default="정량커버만",
                    ),
                    key=f"gieop_quant_{_book_keys(ctx)}",
                    use_container_width=True,
                ):
                    qres = refresh_quant_on_drafts(
                        Path(ctx.root),
                        market=market,
                        candidates=alpha_board.candidates,
                    )
                    st.success(
                        copy_get(
                            "portfolio",
                            "gieop_quant_ok",
                            default=(
                                "정량커버 갱신 {n} · 높음 {h}/중간 {m}/낮음 {l} · "
                                "초안없음 {miss}"
                            ),
                            n=len(qres.get("updated") or []),
                            h=qres.get("n_hi", 0),
                            m=qres.get("n_mid", 0),
                            l=qres.get("n_lo", 0),
                            miss=len(qres.get("missing_draft") or []),
                        )
                    )
                    st.rerun()


def _render_phcvs_watch(ctx: DashboardContext) -> None:
    """PH-CVS 정밀 Review — 확인① 때 갱신된 보드만 표시."""
    from alpha_system.ui.services.phcvs_precision_board import (
        is_attention_row,
        load_precision_board,
        precision_board_html,
    )

    held = list(getattr(ctx, "ops_portfolio_rows", None) or [])
    prop = list(getattr(ctx, "portfolio_rows", None) or [])
    board = load_precision_board(
        ctx.root,
        proposal_rows=prop,
        holdings_rows=held,
    )
    title = copy_get("portfolio", "sec_phcvs", default="정밀 Review")
    attn_n = board.attention_n or sum(1 for r in board.rows if is_attention_row(r))
    fold_bits = [title]
    if attn_n:
        fold_bits.append(f"지금 볼 것 {attn_n}")
    else:
        fold_bits.append("평소 안 펴도 됨")
    with st.expander(" · ".join(fold_bits), expanded=False):
        st.markdown(
            _fold_lead_html(
                purpose=(
                    "PH-CVS 시드 종목 체크리스트 Review입니다. Soft·QVM과 합치지 않습니다."
                ),
                do_now=(
                    copy_get(
                        "portfolio",
                        "phcvs_do_now",
                        default=(
                            "확인 ① 정량·정성 한 번에로 갱신 · "
                            f"{'FAIL/U ' + str(attn_n) + '건만 보면 됨' if attn_n else '즉시 볼 것 없음'}"
                        ),
                    )
                ),
                ignore="학술 P/F 단정 · 자동 매수·편입 · Soft 순위 가산",
            ),
            unsafe_allow_html=True,
        )
        chips: list[tuple[str, str]] = []
        if attn_n:
            chips.append((f"지금 볼 것 {attn_n}", "warn"))
        else:
            chips.append(("즉시 Review 없음", "muted"))
        if board.as_of_prices:
            chips.append((f"가격 {board.as_of_prices}", "muted"))
        chips.append(("Review-only", "muted"))
        _render_section_head(
            title,
            summary=copy_get(
                "portfolio",
                "phcvs_caption",
                default=(
                    "확인 ① 때 자동 채점 · 최종 결론은 사람 · Soft·target 불변"
                ),
            ),
            chips=chips,
            tier="input",
        )
        if not board.available:
            st.caption(
                copy_get(
                    "portfolio",
                    "phcvs_idle",
                    default="아직 채점 없음 · 확인 ① 정량·정성 한 번에를 실행하세요.",
                )
            )
        st.markdown(
            precision_board_html(board, attention_only=False),
            unsafe_allow_html=True,
        )


def _observation_pool_tickers(ctx: DashboardContext, *, band_max: int) -> list[str]:
    """Candidate watch board tickers only — not the full scoreboard universe."""
    from alpha_system.ui.services.rank_watchboard import build_rank_watchboard

    saved = _saved_kr_alpha_rows(ctx)
    board = build_rank_watchboard(
        ctx.scoreboard_rows or [],
        proposal_tickers={str(r.ticker).zfill(6) for r in (ctx.portfolio_rows or [])},
        held_tickers={str(r["ticker"]) for r in saved},
        proposal_band_max=max(1, int(band_max)),
        max_rows=watch_max(
            getattr(ctx, "screen_market", None),
            getattr(ctx, "screen_horizon", None),
        ),
    )
    return [str(r.ticker).zfill(6) for r in board.rows]


def _render_proposal_opendart_gates(ctx: DashboardContext) -> None:
    """OpenDART on the watch pool: 경영참여 게이트 + 최대주주 + Review-only 선행 트리거."""
    from alpha_system.ui.services.cecs_opendart_pack import (
        estimate_watch_calls,
        load_opendart_watch,
        refresh_opendart_proposal_watch,
        watch_needs_refresh,
    )
    from alpha_system.ui.services.dart_quota import load_quota

    band = int(getattr(ctx.cfg.sizing, "target_names", 6) or 6)
    tickers = _observation_pool_tickers(ctx, band_max=band)
    proposal_rows = list(ctx.portfolio_rows or [])
    if not tickers and not proposal_rows:
        return
    if not tickers:
        tickers = [str(r.ticker).zfill(6) for r in proposal_rows]
    names = {
        str(r.ticker).zfill(6): (r.name or r.ticker)
        for r in list(ctx.scoreboard_rows or []) + proposal_rows
    }
    journal = ctx.root / "data" / "alpha_system_journal.jsonl"
    as_of = ctx.as_of if isinstance(ctx.as_of, _date) else _date.today()
    data_dir = _source_dir(ctx)
    from alpha_system.ui.services.opendart_evidence_board import (
        opendart_evidence_html,
        opendart_gates_html,
        opendart_join_html,
        opendart_toolbar_html,
        parse_evidence_board,
    )
    # opendart_gates_html: detail expander only (join has 게이트 병합)
    from alpha_system.ui.services.dart_evidence import (
        evidence_gate_policy_path,
        load_evidence_gate_policy,
        withdrawn_buyback_gate_candidates,
    )
    from alpha_system.shadow.evidence_ab import evidence_ab_report

    snap = load_opendart_watch(ctx.root, data_dir=data_dir)
    need = watch_needs_refresh(snap, tickers)
    quota = load_quota(Path(data_dir))
    policy = load_evidence_gate_policy(evidence_gate_policy_path(Path(data_dir)))
    gate_on = bool(policy.get("enabled"))

    # First-ever: rebuild from disk caches only (0 calls). Network only on button.
    if snap is None:
        try:
                snap = refresh_opendart_proposal_watch(
                    ctx.root,
                    tickers,
                    as_of=as_of,
                    journal_path=journal,
                data_dir=data_dir,
                mode="cache_only",
                )
        except Exception as exc:
            st.warning(f"OpenDART 캐시 로드 실패: {exc}")

    st.markdown(
        opendart_toolbar_html(
            quota_line=quota.status_line(),
            stale=need,
            as_of=str(getattr(snap, "as_of", "") or ""),
            fetched_at=str(getattr(snap, "fetched_at", "") or ""),
            gate_mode_on=gate_on,
        ),
        unsafe_allow_html=True,
    )
    # 일상 갱신=확인 ① · 여기선 위험 전체 재탐색만 접기
    bk = _book_keys(ctx)
    from alpha_system.ui.services.approval_chrome import refresh_action_button

    st.caption(
        copy_get(
            "portfolio",
            "opendart_daily_hint",
            default=(
                "일상 갱신=확인 ① 정량·정성 한 번에(증분·심층·정밀) · "
                "점수·target 불변"
            ),
        )
    )
    if need:
        st.caption(
            copy_get(
                "portfolio",
                "opendart_stale_hint",
                default="캐시 만료 · 확인 ①을 실행하세요.",
            )
        )
    do_force = False
    with st.expander(
        copy_get(
            "portfolio",
            "opendart_force_fold",
            default="드묾 · OpenDART 전체 재탐색(위험)",
        ),
        expanded=False,
    ):
        st.caption(
            copy_get(
                "portfolio",
                "opendart_force_hint",
                default=(
                    f"전 종목 재호출 · 예상 상한 ≈{estimate_watch_calls(len(tickers))}회 · "
                    "일상 증분은 확인 ①"
                ),
            )
        )
        do_force = refresh_action_button(
            copy_get("portfolio", "opendart_btn_force", default="전체 재탐색(위험)"),
            key=f"pf_od_force_{bk}",
            primary=False,
        )
    if do_force:
        try:
            with st.spinner("OpenDART 전체 재탐색 중…"):
                snap = refresh_opendart_proposal_watch(
                    ctx.root,
                    tickers,
                    as_of=as_of,
                    journal_path=journal,
                    data_dir=data_dir,
                    mode="force",
                    enrich_documents=False,
                )
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
            return
    if snap is None:
        return
    if snap.missing_key:
        st.warning("Open DART API 키가 없습니다. 설정에 키를 넣은 뒤 확인 ①을 실행하세요.")

    flags = list(snap.flag_models())
    path = overlay_path(_source_dir(ctx))
    overlay = load_qual_overlay(path)
    if flags:
        updated, applied = apply_opendart_flag_gates(overlay, flags, as_of=as_of)
        if applied:
            save_qual_overlay(path, updated)
            overlay = updated
            for tk in applied:
                journal_overlay_change(
                    action_kind="QUAL_GATE",
                    subject=tk,
                    rationale="OpenDART 경영참여·연기금 자동 제외",
                    as_of=as_of,
                    payload={"source": "opendart_watch", "tickers": list(applied)},
                    journal_path=journal,
                )
            st.rerun()
    gated = overlay.gated_tickers()

    board = parse_evidence_board(getattr(snap, "evidence", None) or [])
    blocked_rows = list(getattr(ctx, "proposal_blocked_rows", None) or [])
    gate_cands = withdrawn_buyback_gate_candidates(board)
    ab = None
    if gate_cands:
        prop_tks = [str(r.ticker).zfill(6) for r in proposal_rows]
        score_map = {
            str(r.ticker).zfill(6): float(getattr(r, "total_score", 0) or 0)
            for r in list(ctx.scoreboard_rows or [])
            if getattr(r, "ticker", None)
        }
        ab = evidence_ab_report(
            prop_tks or [b.ticker for b in board],
            [tk for tk, _ in gate_cands],
            score_by_ticker=score_map,
        )
    # Screen-pool PH-CVS-style verify (not PDF 7 names) — same glance as proposal.
    from alpha_system.review.screen_deep_verify import (
        MODEL_VERSION as SCREEN_DEEP_MODEL,
        build_screen_verify,
        load_screen_verify,
        save_screen_verify,
        screen_verify_attention_html,
    )
    sv_board = load_screen_verify(Path(data_dir))
    want_tks = list(
        dict.fromkeys(
            tickers
            + [str(r.ticker).zfill(6) for r in proposal_rows]
            + [str(r.ticker).zfill(6) for r in blocked_rows]
        )
    )
    # 심층은 확인 ①에서 persist · 여기선 캐시 없거나 집합 불일치 때만 로컬 재구성
    if (
        not sv_board.available
        or sv_board.model_version != SCREEN_DEEP_MODEL
        or {r.ticker for r in sv_board.rows} != set(want_tks)
    ):
        try:
            sv_board = build_screen_verify(
                ctx.root,
                data_dir=Path(data_dir),
                tickers=want_tks,
                names=names,
                proposal_tickers=[str(r.ticker).zfill(6) for r in proposal_rows],
                blocked_tickers=[str(r.ticker).zfill(6) for r in blocked_rows],
                opendart_watch={
                    "evidence": list(getattr(snap, "evidence", None) or []),
                    "flags": list(getattr(snap, "flags", None) or []),
                    "metrics": list(getattr(snap, "metrics", None) or []),
                },
                min_hits=int(getattr(ctx.cfg.sizing, "hakedaka_min_hits", 2) or 2),
                as_of=str(getattr(snap, "as_of", "") or as_of.isoformat()),
            )
            save_screen_verify(Path(data_dir), sv_board)
        except Exception as exc:  # noqa: BLE001
            st.warning(f"스크린 심층 검증 실패: {exc}")
    attn = screen_verify_attention_html(sv_board)
    if attn:
        st.markdown(attn, unsafe_allow_html=True)
    for r in sv_board.rows:
        if r.ticker and r.ticker not in names:
            names[r.ticker] = r.name or r.ticker
    # One glance table — PDF-7 PH-CVS stays in bottom expander only.
    st.markdown(
        opendart_join_html(
            proposal_rows=proposal_rows,
            blocked_rows=blocked_rows,
            scoreboard_rows=list(ctx.scoreboard_rows or []),
            board=board,
            flags=flags,
            gated=set(gated),
            names=names,
            screen_verify_rows=list(sv_board.rows),
        ),
        unsafe_allow_html=True,
    )
    with st.expander("상세 · 게이트 메모 · 공시 건별", expanded=False):
        if flags:
            st.markdown(
                opendart_gates_html(flags, names=names, gated=set(gated)),
                unsafe_allow_html=True,
            )
        st.markdown(
            opendart_evidence_html(
                board,
                names=names,
                withdrawn_tickers=[tk for tk, _ in gate_cands],
                ab=ab,
                gate_mode_on=gate_on,
                show_attn=False,
            ),
            unsafe_allow_html=True,
        )

    if (
        gate_on
        and policy.get("exclude_withdrawn_buyback", True)
        and gate_cands
    ):
        updated, applied = apply_evidence_withdrawn_gates(
            overlay, gate_cands, as_of=as_of
        )
        if applied:
            save_qual_overlay(path, updated)
            for tk in applied:
                journal_overlay_change(
                    action_kind="QUAL_GATE",
                    subject=tk,
                    rationale="증거 게이트: 자사주 체인 최종 철회",
                    as_of=as_of,
                    payload={"source": "evidence_withdrawn", "tickers": list(applied)},
                    journal_path=journal,
                )
            st.info(
                copy_get(
                    "portfolio",
                    "opendart_evidence_gated",
                    default="증거 게이트 ON · 자사주 철회 {n}종 제안 제외(점수 불변).",
                    n=len(applied),
                )
            )
            st.rerun()


def _render_proposal_target_board(ctx: DashboardContext) -> None:
    """Justified P/B auto-apply on the confirmed book → exit YAML only."""
    rows = list(ctx.portfolio_rows or [])
    if not rows:
        return
    from alpha_system.ui.services.weekly_domain_gates import auto_apply_proposal_quant_targets

    as_of = ctx.as_of if isinstance(ctx.as_of, _date) else _date.today()
    journal = ctx.root / "data" / "alpha_system_journal.jsonl"
    exit_yaml_path = Path(ctx.root) / "data" / "kr_alpha_exit_targets.yaml"
    try:
        from alpha_system.screen_book import operational_data_dir

        mkt = str(getattr(ctx, "screen_market", None) or "KOSPI")
        hz = str(getattr(ctx, "screen_horizon", None) or "mid")
        exit_yaml_path = (
            operational_data_dir(Path(ctx.root), mkt, hz)
            / "kr_alpha_exit_targets.yaml"
        )
    except Exception:  # noqa: BLE001
        pass
    result = auto_apply_proposal_quant_targets(
        root=ctx.root,
        rows=rows,
        as_of=as_of,
        journal_path=journal,
        exit_targets_path=exit_yaml_path,
    )
    if result.get("applied"):
        st.rerun()

    skipped = list(result.get("skipped") or [])
    if skipped:
        st.warning(f"정량 초안 불가 (ROE·PBR·섹터 부족): {', '.join(skipped)} · 편입 차단")


def _esc_pf(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _chips_html(chips: list[tuple[str, str]] | None) -> str:
    if not chips:
        return ""
    bits = [
        f'<span class="pf-sec-chip pf-sec-chip-{_esc_pf(tone)}">{_esc_pf(label)}</span>'
        for label, tone in chips
    ]
    return f'<div class="pf-sec-chips">{"".join(bits)}</div>'


def _render_section_head(
    title: str,
    *,
    summary: str = "",
    chips: list[tuple[str, str]] | None = None,
    extra_html: str = "",
    tier: str = "",
) -> None:
    """Section header inside the outer container (no nested outer frame)."""
    summary_html = (
        f'<div class="pf-sec-summary">{_esc_pf(summary)}</div>' if summary else ""
    )
    tier_cls = f" pf-sec-head-{_esc_pf(tier)}" if tier else ""
    st.markdown(
        f'<div class="pf-sec-head{tier_cls}">'
        f'<div class="pf-sec-title">{_esc_pf(title)}</div>'
        f"{summary_html}{_chips_html(chips)}{extra_html}"
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_control_card(label: str, *, hint: str = "") -> None:
    """Control label row inside the section (not a separate box)."""
    hint_html = (
        f'<span class="pf-ctl-hint">{_esc_pf(hint)}</span>' if hint else ""
    )
    st.markdown(
        f'<div class="pf-ctl-row">'
        f'<span class="pf-ctl-label">{_esc_pf(label)}</span>'
        f"{hint_html}</div>",
        unsafe_allow_html=True,
    )


def _render_status_card(body: str, *, tone: str = "muted") -> None:
    st.markdown(
        f'<div class="pf-status pf-status-{_esc_pf(tone)}">'
        f"{_esc_pf(body)}</div>",
        unsafe_allow_html=True,
    )


def _proposal_map_html(
    *,
    short: bool,
    quality_sort: bool,
    n_eligible: int,
    n_blocked: int,
    n_held: int,
) -> str:
    if short:
        tiles = [
            ("사도 됨", str(n_eligible), "단기 편입", "모멘텀 Soft 통과", "ok"),
            ("지금은 안 삼", str(n_blocked), "대기·제외", "조건 미달 · 비중 0", "warn"),
            ("단기 보유", str(n_held), "이미 든 것", "유지·축소·교체", "muted"),
        ]
        if n_eligible == 0 and n_blocked > 0:
            yolk = (
                f"편입 0 · 대기 {n_blocked} = 단기 Soft/게이트로 막힘 · "
                "오늘은 중기·파킹만 · 대기 종목 신규 매수 금지"
            )
        elif n_eligible == 0:
            yolk = "단기 편입 없음 · 접어 두고 중기만 봐도 됨"
        else:
            yolk = "단기=위성 · 중기 QVM과 섞지 않음 · 하루≤33% · 사람만 주문"
    else:
        tiles = [
            ("사도 됨", str(n_eligible), "중기 편입", "목표 자리·카드", "ok"),
            ("지금은 안 삼", str(n_blocked), "노른자 대기", "비싸거나 게이트", "warn"),
            ("중기 보유", str(n_held), "이미 든 것", "집합 대조와 다를 수 있음", "muted"),
        ]
        yolk = (
            "대기(노른자)=고Q인데 지금은 안 삼 · "
            "보유 전부 ≠ 노른자 · 매매 순서는 맨 위「오늘 매매」"
        )
        if quality_sort:
            yolk = "편입 목록 Q↓·하케다카↓ · " + yolk
    cells = "".join(
        f'<div class="pf-map-cell pf-map-{tone}">'
        f'<div class="pf-map-k">{_esc_pf(k)}</div>'
        f'<div class="pf-map-n">{_esc_pf(n)}</div>'
        f'<div class="pf-map-tag">{_esc_pf(tag)}</div>'
        f'<div class="pf-map-body">{_esc_pf(body)}</div>'
        f"</div>"
        for k, n, tag, body, tone in tiles
    )
    note = (
        f'<div class="pf-map-note">{_esc_pf(yolk)}</div>' if yolk else ""
    )
    return f'<div class="pf-map">{cells}</div>{note}'


def _proposal_empty_message(
    *,
    short: bool,
    n_blocked: int,
    n_data: int = 0,
    n_soft: int = 0,
) -> str:
    if short and n_blocked > 0:
        if n_data > 0 and n_soft == 0 and n_data >= n_blocked:
            return copy_get(
            "portfolio",
                "proposal_final_empty_short_data",
            default=(
                    "단기 편입 0 · 대기 {n}은 일봉·데이터 부족으로 판정 보류입니다. "
                    "확인에서 일봉 채운 뒤 재판정 · Soft 미달(전략 탈락)과 다릅니다. "
                    "합격선 고장이 아닙니다."
                ),
                n=n_blocked,
            )
        if n_data > 0:
            return copy_get(
                "portfolio",
                "proposal_final_empty_short_mixed",
                default=(
                    "단기 편입 0 · 대기 {n} (데이터 보류 {d} · Soft/게이트 미달 {s}). "
                    "보류는 갱신 후 재판정 · 미달은 지금은 안 삼 · 중기·파킹 유지. "
                    "합격선 고장이 아닙니다."
                ),
                n=n_blocked,
                d=n_data,
                s=n_soft,
            )
        return copy_get(
            "portfolio",
            "proposal_final_empty_short_blocked",
            default=(
                "단기 편입 0종 · 아래 대기 {n}은 Soft/게이트로 막혀 "
                "지금은 사지 않습니다. 접어 두고 중기·파킹만 보세요. "
                "합격선 고장이 아닙니다."
            ),
            n=n_blocked,
        )
    if short:
        return copy_get(
            "portfolio",
            "proposal_final_empty_short",
            default=(
                "단기 편입 후보 없음 · 정량을 안 돌렸거나 Soft 통과분이 없습니다. "
                "중기만 운영해도 됩니다."
            ),
        )
    if n_blocked > 0:
        return copy_get(
            "portfolio",
            "proposal_final_empty_blocked",
            default=(
                "중기 편입 0종 · 아래 대기 {n}은 게이트·목표가 등으로 제외. "
                "대기=비중 없음 · 사람만 Review."
            ),
            n=n_blocked,
        )
    return copy_get(
        "portfolio",
        "proposal_final_empty",
        default="편입 후보 없음 · 확인에서 정량 후 후보·합격선을 보세요.",
    )


def _holdings_sell_actions(ctx: DashboardContext) -> list:
    """Ops rows with stance=매도, priority-sorted (strongest first)."""
    try:
        from alpha_system.ui.services.proposal_chart_board import reads_by_ticker
        from alpha_system.ui.services.weight_action import build_weight_actions_for_rows
    except Exception:  # noqa: BLE001
        return []
    rows = list(getattr(ctx, "ops_portfolio_rows", None) or [])
    if not rows:
        return []
    flow_data_dir = Path(
        getattr(ctx, "source_data_dir", None) or (Path(ctx.root) / "data")
    )
    try:
        chart_map = reads_by_ticker(ctx)
    except Exception:  # noqa: BLE001
        chart_map = {}
    try:
        pairs = build_weight_actions_for_rows(
            rows, chart_map=chart_map, flow_data_dir=flow_data_dir
        )
    except Exception:  # noqa: BLE001
        return []
    sells = [(r, a) for r, a in pairs if a.stance == "매도"]
    sells.sort(key=lambda t: (t[1].priority, -(t[1].move_pct or 0)))
    return sells


def _holdings_sell_pressure(ctx: DashboardContext) -> bool:
    return bool(_holdings_sell_actions(ctx))


def _render_next_buy_queue(ctx: DashboardContext) -> None:
    """중기 「다음 순매수」— 오늘 비중 아래. A→B Review 한 줄. 단기 스킵."""
    if is_short(getattr(ctx, "screen_horizon", None)):
        return
    try:
        from alpha_system.ui.services.next_buy_queue import (
            build_next_buy_queue,
            enrich_scoreboard_prices,
            format_rotation_ab_hint,
            next_buy_board_html,
        )
    except Exception:  # noqa: BLE001
        return
    scoreboard = list(getattr(ctx, "scoreboard_rows", None) or [])
    if not scoreboard:
        return
    proposal = list(getattr(ctx, "portfolio_rows", None) or [])
    held = list(getattr(ctx, "ops_portfolio_rows", None) or [])
    blocked = list(getattr(ctx, "proposal_blocked_rows", None) or [])
    enriched = enrich_scoreboard_prices(scoreboard, proposal, held, blocked)
    sells = _holdings_sell_actions(ctx)
    sell_pressure = bool(sells)
    ma_map: dict[str, str] = {}
    try:
        from alpha_system.proposal_chart import load_cached_charts, norm_ticker as _nt

        board = load_cached_charts(Path(ctx.root), str(getattr(ctx, "market", "KOSPI") or "KOSPI"))
        if board is not None:
            for it in board.items or []:
                lab = str(getattr(it, "ma_label", "") or "")
                tk = _nt(getattr(it, "ticker", ""))
                if tk and lab:
                    ma_map[tk] = lab
    except Exception:  # noqa: BLE001
        ma_map = {}
    queue = build_next_buy_queue(
        scoreboard=enriched,
        proposal_rows=proposal,
        held_rows=held,
        sell_pressure=sell_pressure,
        top_k=8,
        exclude_proposal=True,
        ma_label_by_ticker=ma_map or None,
    )
    rotation_hint = ""
    if sell_pressure:
        row_a, act_a = sells[0]
        buy_b = queue.items[0] if queue.items else None
        rotation_hint = format_rotation_ab_hint(
            sell_name=str(getattr(row_a, "name", "") or ""),
            sell_ticker=str(getattr(row_a, "ticker", "") or ""),
            sell_pct=float(act_a.move_pct or 0),
            buy=buy_b,
            buy_cum_cap=67.0,
            day_cap=33.0,
        )
    title = copy_get("portfolio", "next_buy_title", default="다음 순매수")
    legend = copy_get(
        "portfolio",
        "next_buy_legend",
        default="제안 N 유지 · 미보유·목표가↓ · 점수순 · Review-only · target 불변",
    )
    sell_hint = copy_get(
        "portfolio",
        "next_buy_sell_hint",
        default="여유·교체 검토 · 상위부터 무릎 매수 Review · 자동주문 없음",
    )
    st.markdown(
        next_buy_board_html(
            queue,
            title=title,
            legend=legend,
            sell_hint=sell_hint,
            rotation_hint=rotation_hint,
        ),
        unsafe_allow_html=True,
    )
    st.caption(
        copy_get(
            "portfolio",
            "next_buy_caption",
            default=(
                "매도 시 순환 Review(A→B) · B 오늘≤33% · 잔여 현금/단기채 · "
                "제안 N 유지 · 사람만 · docs/ROTATION_A_TO_B_RULE"
            ),
        )
    )


def _render_proposal_book(
    ctx: DashboardContext,
    *,
    proposal_eligible_sorter: Callable[
        [list[PortfolioRow], DashboardContext], list[PortfolioRow]
    ]
    | None = None,
    proposal_final_sort_label: str | None = None,
    section_kicker: str | None = None,
) -> None:
    short = is_short(getattr(ctx, "screen_horizon", None))
    with st.container(border=True):
        eligible = list(ctx.portfolio_rows or [])
        if proposal_eligible_sorter and eligible:
            eligible = proposal_eligible_sorter(eligible, ctx)
        blocked = list(getattr(ctx, "proposal_blocked_rows", None) or [])
        held_n = len(getattr(ctx, "ops_portfolio_rows", None) or [])
        if short:
            sec_title = copy_get(
                "portfolio", "sec_proposal_short", default="단기 제안"
            )
            summary = copy_get(
                "portfolio",
                "screen_book_caption_short",
                default=(
                    "위성만 · 중기와 섞지 않음 · 편입=사도 됨 · "
                    "대기=지금은 안 삼 · 사람만 주문"
                ),
            )
        else:
            sec_title = copy_get(
                "portfolio", "sec_proposal", default="제안 · 할 일"
            )
            if section_kicker:
                sec_title = f"{section_kicker} · {sec_title}"
            summary = copy_get(
                "portfolio",
                "screen_book_caption",
                default=(
                    "편입=사도 됨 · 대기=지금은 안 삼 · "
                    "카드=Review · 사람만 주문"
                ),
            )
        _render_section_head(
            sec_title,
            summary=summary,
            chips=[
                (f"사도 됨 {len(eligible)}", "ok"),
                (f"안 삼 {len(blocked)}", "warn"),
            ],
            tier="primary",
            extra_html=_proposal_map_html(
                short=short,
                quality_sort=bool(proposal_final_sort_label),
                n_eligible=len(eligible),
                n_blocked=len(blocked),
                n_held=held_n,
            ),
        )
        if short and not eligible:
            st.markdown(
                _fold_lead_html(
                    purpose=(
                        "단기 위성 제안 칸입니다. 중기 Core·목표가 환금과 "
                        "다른 장부입니다."
                    ),
                    do_now=(
                        f"편입 0 · 대기 {len(blocked)} → 단기 신규는 쉬고 "
                        "중기·파킹만. 대기 목록은 ‘왜 막혔는지’ 참고용."
                        if blocked
                        else "단기 후보 없음 · 이 접기 닫고 중기만 보세요."
                    ),
                    ignore="합격선 고장으로 단정 · 대기 종목 추격 매수 · 중기 전량",
                ),
                unsafe_allow_html=True,
            )
        with st.expander(
            copy_get(
                "portfolio",
                "sec_proposal_evidence_short" if short else "sec_proposal_evidence",
                default=(
                    "왜 막혔는지 · 섹터·게이트 (평소 안 펴도 됨)"
                    if short
                    else "근거 · 섹터·게이트·목표가"
                ),
            ),
            expanded=False,
        ):
            st.markdown(
                _fold_lead_html(
                    purpose="편입/대기 숫자 아래의 기술 근거만 모았습니다.",
                    do_now="궁금한 게이트·섹터만 · 매매 순서는 맨 위「오늘 매매」.",
                    ignore="여기 표로 자동매도·target 기입",
                ),
                unsafe_allow_html=True,
            )
            _render_sector_exposure(ctx)
            _render_revalidate_flags(ctx)
            _render_proposal_opendart_gates(ctx)
            if not short:
                _render_proposal_target_board(ctx)
            else:
                st.caption(
                    copy_get(
                        "portfolio",
                        "ops_cue_short_caption",
                        default=(
                            "단기 배지: 제안 밖·모멘텀 붕괴=교체 · "
                            "약화=축소 · 중기 목표가 미사용 · 자동매도 없음"
                        ),
                    )
                )
        final_heading = copy_get(
            "portfolio",
            "proposal_final_heading_short" if short else "proposal_final_heading",
            default="사도 되는 단기" if short else "편입 · 목표 자리",
        )
        if proposal_final_sort_label and not short:
            final_heading = f"{final_heading} · {proposal_final_sort_label}"
        st.markdown(
            f'<div class="pf-group-kicker">'
            f'<span class="pf-group-badge pf-group-ok">편입</span> '
            f"{final_heading}"
            f" · {len(eligible)}"
            f"</div>",
            unsafe_allow_html=True,
        )
        if eligible:
            from alpha_system.ui.services.proposal_chart_board import render_proposal_chart_refresh

            render_proposal_chart_refresh(ctx, eligible)
        if not short:
            from alpha_system.ui.services.mid_cross_verify import render_mid_cross_verify

            render_mid_cross_verify(ctx)
        data_n, soft_n, _other_n = _blocked_bucket_counts(ctx)
        if not eligible:
            st.info(
                _proposal_empty_message(
                    short=short,
                    n_blocked=len(blocked),
                    n_data=data_n,
                    n_soft=soft_n,
                )
            )
        else:
            render_portfolio_bullets(
                ctx,
                mode="full",
                key_prefix=f"pf_proposal_{_book_keys(ctx)}",
                rows=eligible,
                always_open=True,
            )
        if blocked:
            blocked_head = copy_get(
                "portfolio",
                "proposal_blocked_heading_short" if short else "proposal_blocked_heading",
                default="지금은 안 사는 단기" if short else "편입하지 않음",
            )
            if not short:
                blocked_head = f"{blocked_head} · 노른자 대기"
            st.markdown(
                f'<div class="pf-group-kicker">'
                f'<span class="pf-group-badge pf-group-warn">대기</span> '
                f"{blocked_head}"
                f" · {len(blocked)}"
                f"</div>",
                unsafe_allow_html=True,
            )
            if short and (data_n or soft_n):
                blocked_cap = copy_get(
                    "portfolio",
                    "proposal_blocked_caption_short_split",
                    default=(
                        "판정 보류(일봉·데이터) {d} · Soft/게이트 미달 {s} · "
                        "비중 없음 · 보류≠탈락 · 추격 매수 금지"
                    ),
                    d=data_n,
                    s=soft_n,
                )
            else:
                blocked_cap = copy_get(
                    "portfolio",
                    "proposal_blocked_caption_short" if short else "proposal_blocked_caption",
                    default=(
                        "모멘텀 Soft·게이트 미달 · 비중 없음 · 추격 매수 금지"
                        if short
                        else "점수 상위이나 지금은 편입 안 함 · 비중 없음"
                    ),
                )
            st.caption(blocked_cap)
            render_portfolio_bullets(
                ctx,
                mode="full",
                key_prefix=f"pf_blocked_{_book_keys(ctx)}",
                rows=blocked,
            )


def _fold_lead_html(
    *,
    purpose: str,
    do_now: str,
    ignore: str = "",
) -> str:
    """접기 본문 맨 위 — 왜 있는지 / 지금 / 무시."""
    ignore_html = (
        f'<div class="pf-fold-row pf-fold-ignore">'
        f'<span class="pf-fold-lab">무시</span>'
        f"<span>{_esc(ignore)}</span></div>"
        if ignore
        else ""
    )
    return (
        '<div class="pf-fold-lead" role="note">'
        f'<div class="pf-fold-row">'
        f'<span class="pf-fold-lab">이 칸</span>'
        f"<span>{_esc(purpose)}</span></div>"
        f'<div class="pf-fold-row pf-fold-do">'
        f'<span class="pf-fold-lab">지금</span>'
        f"<span>{_esc(do_now)}</span></div>"
        f"{ignore_html}"
        "</div>"
    )


def _fold_block_html(title: str, blurb: str) -> str:
    """접기 안 소절 제목."""
    return (
        f'<div class="pf-fold-block">'
        f'<div class="pf-fold-block-h">{_esc(title)}</div>'
        f'<div class="pf-fold-block-b">{_esc(blurb)}</div>'
        f"</div>"
    )


def _activist_ops_block_html(
    ctx: DashboardContext,
    *,
    root: Path | None = None,
) -> str:
    """행동주의 Review 사/유지/팔 — Soft와 분리 블록."""
    if is_short(getattr(ctx, "screen_horizon", None)):
        return ""
    base = Path(root or getattr(ctx, "root", ".") or ".")
    mkt = str(getattr(ctx, "screen_market", None) or "KOSPI")
    try:
        from alpha_system.review.treasury_activist_proposal import (
            activist_membership_sets,
            build_activist_proposal,
            load_activist_held_tickers,
        )
        from alpha_system.ui.services.alpha_book_ops import (
            activist_today_buy_names_max,
            load_alpha_book_ops,
        )

        soft_tks = [
            str(getattr(r, "ticker", "") or "").zfill(6)
            for r in (ctx.portfolio_rows or [])
            if str(getattr(r, "ticker", "") or "").strip("0")
        ]
        pol = load_alpha_book_ops(base)
        today_a = int(activist_today_buy_names_max(policy=pol))
        board = build_activist_proposal(
            base,
            market=mkt,
            soft_tickers=soft_tks,
            today_buy_names_max=today_a,
        )
        held = load_activist_held_tickers(
            base, positions_path=Path(ctx.data_dir) / "positions.csv"
        )
        both, prop_only, held_only = activist_membership_sets(
            proposal_tickers=board.tickers,
            held_activist_tickers=held,
        )
    except Exception:  # noqa: BLE001
        return ""

    name_by = {r.ticker: r.name for r in board.rows}
    pct_by = {r.ticker: r.of_mid_soft_pct for r in board.rows}

    def _chip(tk: str) -> str:
        nm = name_by.get(tk, tk)
        short = nm if len(nm) <= 8 else nm[:7] + "…"
        pct = pct_by.get(tk)
        tip = f"{nm} ({tk})" + (f" · Soft대비 {pct}%" if pct is not None else "")
        return (
            f'<span class="pf-set-chip" title="{_esc(tip)}">{_esc(short)}</span>'
        )

    def _col(title: str, todo: str, keys: list[str], tone: str) -> str:
        chips = "".join(_chip(k) for k in keys) or (
            '<span class="pf-set-empty">없음</span>'
        )
        return (
            f'<div class="pf-set-col pf-set-{_esc(tone)}">'
            f'<div class="pf-set-h">{_esc(title)} · {len(keys)}</div>'
            f'<div class="pf-set-todo">{_esc(todo)}</div>'
            f'<div class="pf-set-chips">{chips}</div>'
            f"</div>"
        )

    skip_n = len(board.skipped_soft or [])
    skip_note = (
        f" · Soft겹침 제외 {skip_n}종" if skip_n else ""
    )
    buy_todo = (
        f"신규 Review · 오늘≤{board.today_buy_names_max}종 · "
        f"단계 {board.active_stage} · 자리 {board.active_seat_pct:g}% · "
        f"합≈{board.of_mid_sum():g}% Soft대비 · HTS"
    )
    return (
        '<div class="pf-set-board pf-activist-set" role="group" '
        'aria-label="행동주의 Soft 이원 매매">'
        '<div class="pf-set-kicker">'
        f"행동주의 Review · Soft 이원 · 테마 {board.theme_of_mid_soft_pct:g}% "
        f"of Soft{skip_note} · style=treasury_activist · target 불변"
        "</div>"
        '<div class="pf-set-grid">'
        + _col("둘 다", "유지 · 해부·공시 후 자리% 상향 Review", both, "ok")
        + _col("제안만", buy_todo, prop_only, "buy")
        + _col(
            "보유만",
            "배지·촉매 소멸 Review · Soft와 합산 주문 금지",
            held_only,
            "sell",
        )
        + "</div>"
        '<div class="pf-set-tip">'
        "승격 picks → 여기 집합 · Soft 블록과 한 줄로 합치지 않음 · "
        "미집행=단기채 · 자동주문 없음"
        "</div>"
        "</div>"
    )


def _membership_set_board_html(
    ctx: DashboardContext,
) -> str:
    """제안∩보유 / 제안만 / 보유만 — 티커 집합 대조 (평단·% 불필요)."""
    both, prop_only, held_only, src = _membership_sets(ctx)
    above = _above_target_set(ctx)
    prop = {
        k: src[k]
        for k in list(prop_only) + list(both)
        if k in src
    }
    held = {
        k: src[k]
        for k in list(held_only) + list(both)
        if k in src
    }

    def _cell(tk: str, row: object) -> str:
        name = str(getattr(row, "name", "") or tk).strip() or tk
        short = name if len(name) <= 8 else name[:7] + "…"
        tip = _held_only_todo(tk, row, above=above) if tk in held_only else name
        return (
            f'<span class="pf-set-chip" title="{_esc(tip)} ({_esc(tk)})">'
            f"{_esc(short)}</span>"
        )

    def _col(
        title: str,
        todo: str,
        keys: list[str],
        bag: dict[str, object],
        tone: str,
    ) -> str:
        chips = "".join(_cell(k, bag[k]) for k in keys if k in bag) or (
            '<span class="pf-set-empty">없음</span>'
        )
        return (
            f'<div class="pf-set-col pf-set-{_esc(tone)}">'
            f'<div class="pf-set-h">{_esc(title)} · {len(keys)}</div>'
            f'<div class="pf-set-todo">{_esc(todo)}</div>'
            f'<div class="pf-set-chips">{chips}</div>'
            f"</div>"
        )

    held_todo = "배지별 Review · 목표가 도달=환금 · 탈락=전량 · 데이터=보류"
    if held_only:
        samples = [
            _held_only_todo(tk, src[tk], above=above)
            for tk in held_only[:2]
            if tk in src
        ]
        if samples:
            held_todo = " · ".join(samples[:2])

    return (
        '<div class="pf-set-board" role="group" '
        'aria-label="제안과 보유 집합 대조">'
        '<div class="pf-set-kicker">'
        "종목 할 일 · 집합+배지 · 보유만≠무조건 전량"
        "</div>"
        '<div class="pf-set-grid">'
        + _col(
            "둘 다",
            "유지 · 적합도≥50%면 추매 Review",
            both,
            src,
            "ok",
        )
        + _col(
            "제안만",
            "신규 중 오늘 집행 0–2종 · 적합도% · 하루≤33% · 제안 N≠전량매수 · 미집행=단기채",
            prop_only,
            prop,
            "buy",
        )
        + _col(
            "보유만",
            held_todo,
            held_only,
            held,
            "sell",
        )
        + "</div>"
        '<div class="pf-set-tip">'
        "운영=집합+배지 최종수량(강한 쪽·합산 아님) · 금액·부분체결은 HTS · "
        "목표바 %로 계좌 맞추지 않음 · 자동주문·target 불변"
        "</div>"
        "</div>"
    )


def _render_holdings_book(
    ctx: DashboardContext,
    *,
    section_kicker: str | None = None,
    show_set_board: bool = True,
) -> None:
    short = is_short(getattr(ctx, "screen_horizon", None))
    with st.container(border=True):
        held_rows = list(getattr(ctx, "ops_portfolio_rows", None) or [])
        prop_tks = {
            str(getattr(r, "ticker", "") or "").zfill(6)
            for r in (ctx.portfolio_rows or [])
        }
        overlap_n = sum(
            1
            for r in held_rows
            if str(getattr(r, "ticker", "") or "").zfill(6) in prop_tks
        )
        hold_chips: list[tuple[str, str]] = [
            (f"보유 티커 {len(held_rows)}", "muted"),
            (f"둘 다 {overlap_n}", "ok"),
            (
                f"제안만 {max(0, len(prop_tks) - overlap_n)}",
                "warn",
            ),
        ]
        sec_title = copy_get("portfolio", "sec_holdings", default="보유 · 보조")
        if section_kicker:
            sec_title = f"{section_kicker} · {sec_title}"
        _render_section_head(
            sec_title,
            summary=copy_get(
                "portfolio",
                "holdings_caption_short" if short else "holdings_caption",
                default="집합은 위 · 여기는 Shadow·상세(접기) · 평단·% 없음",
            ),
            chips=hold_chips,
            tier="primary",
        )
        if show_set_board:
            st.markdown(_membership_set_board_html(ctx), unsafe_allow_html=True)
        _render_rank_hysteresis_board(ctx)
        _render_weight_action_board(ctx)
        with st.expander(
            copy_get(
                "portfolio",
                "holdings_extra_fold",
                default="심화 참고 · 평소엔 안 펴도 됨",
            ),
            expanded=False,
        ):
            st.markdown(
                _fold_lead_html(
                    purpose=(
                        "맨 위「오늘 매매」·집합으로 부족한 보조만 모았습니다. "
                        "여기 문장이 매매 순서를 뒤집지 않습니다."
                    ),
                    do_now=(
                        "필요할 칸만: 거시 태도 한 줄 → 다음 살 후보 → "
                        "보유 카드 상세. Shadow·급락 이력은 궁금할 때만."
                    ),
                    ignore=(
                        "가상 손익 KPI · L3 버튼 · Soft 전문 용어 · "
                        "target 자동 기입"
                    ),
                ),
                unsafe_allow_html=True,
            )
            if not short:
                st.markdown(
                    _fold_block_html(
                        "A. 거시 태도",
                        "나침반과 같은 Soft · 줄임/늘림 힌트만 · 종목 배지보다 약함",
                    ),
                    unsafe_allow_html=True,
                )
                _render_stance_decision(ctx)
            _render_monthly_rebal_note(ctx)
            if not short:
                st.markdown(
                    _fold_block_html(
                        "B. 다음 살 후보",
                        "매도 여유 생기면 볼 대기열 · 오늘 바로 올인 아님 · ≤33%",
                    ),
                    unsafe_allow_html=True,
                )
                _render_next_buy_queue(ctx)
                st.markdown(
                    _fold_block_html(
                        "C. 가상 손익 (연습장)",
                        "실제 계좌 아님 · 사이드바 백테스트와 같은 계열 · 주문 지시 없음",
                    ),
                    unsafe_allow_html=True,
                )
                _render_shadow_profit_card(ctx)
                st.markdown(
                    _fold_block_html(
                        "D. 급락 이력",
                        "과거 C1–C3 참고 · 버튼 눌러야 계산 · 전량 강제 아님",
                    ),
                    unsafe_allow_html=True,
                )
                _render_l3_history_review(ctx)
            st.markdown(
                _fold_block_html(
                    "E. 보유 카드 상세",
                    "종목별 배지·근거 · 할 일은 왼쪽 배지(유지/줄이기/환금/전량)",
                ),
                unsafe_allow_html=True,
            )
        render_portfolio_bullets(
            ctx,
            mode="full",
                key_prefix=f"pf_ops_{_book_keys(ctx)}",
            rows=list(ctx.ops_portfolio_rows or []),
                empty_hint=(
                    "실보유 티커 없음 · 후보「보유」체크 또는 티커 업로드"
                ),
        )


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _exec_fitness_maps(ctx: DashboardContext) -> dict:
    """Soft·논리·해부 맵 · 실패 시 빈 dict (보드만 약화, 페이지 유지)."""
    from alpha_system.proposal_chart import norm_ticker

    soft_tickers: set[str] = set()
    soft_scores: dict[str, float | None] = {}
    for r in list(getattr(ctx, "portfolio_rows", None) or []):
        tk = norm_ticker(getattr(r, "ticker", None))
        if not tk:
            continue
        soft_tickers.add(tk)
        try:
            sc = getattr(r, "total_score", None)
            soft_scores[tk] = float(sc) if sc is not None and sc != "" else None
        except (TypeError, ValueError):
            soft_scores[tk] = None
    value_pass: dict[str, bool] = {}
    quality_pass: dict[str, bool] = {}
    gieop_gates: dict[str, str] = {}
    try:
        from alpha_system.ui.services.gieop_observe_board import (
            load_observe_ui_board,
            resolve_gieop_paths,
        )
        from alpha_system.ui.services.gieop_verdict import load_verdicts

        market = str(getattr(ctx, "screen_market", None) or "KOSPI")
        board = load_observe_ui_board(Path(ctx.root), market=market)
        for row in list(getattr(board, "deep_pick", None) or []) + list(
            getattr(board, "watch_top", None) or []
        ):
            tk = norm_ticker(getattr(row, "ticker", None))
            if not tk:
                continue
            if getattr(row, "pass_value", None) is not None:
                value_pass[tk] = bool(row.pass_value)
        paths = resolve_gieop_paths(Path(ctx.root))
        for tk, v in load_verdicts(paths.drafts_dir).items():
            gieop_gates[norm_ticker(tk)] = str(v.effective_gate or "")
    except Exception:  # noqa: BLE001
        pass
    return {
        "soft_tickers": soft_tickers,
        "soft_scores": soft_scores,
        "value_pass": value_pass,
        "quality_pass": quality_pass,
        "gieop_gates": gieop_gates,
    }


def _render_exec_fitness_board(ctx: DashboardContext) -> None:
    """오늘 매매 상단 · 적합도%·오늘% (O/X 대체)."""
    try:
        from alpha_system.ui.services.exec_fitness import (
            build_fitness_board_rows,
            exec_fitness_board_html,
        )
        from alpha_system.ui.services.proposal_chart_board import reads_by_ticker
        from alpha_system.ui.services.weight_action import (
            board_items,
            build_weight_actions_for_rows,
        )

        held = list(getattr(ctx, "ops_portfolio_rows", None) or [])
        prop = list(getattr(ctx, "portfolio_rows", None) or [])
        # 보유 액션 + 제안만(미보유) 추가 후보
        held_tk = {
            str(getattr(r, "ticker", "") or "").zfill(6) for r in held
        }
        buy_candidates = [
            r
            for r in prop
            if str(getattr(r, "ticker", "") or "").zfill(6) not in held_tk
        ]
        rows = held + buy_candidates
        if not rows:
            st.markdown(exec_fitness_board_html([]), unsafe_allow_html=True)
            st.caption(
                copy_get(
                    "portfolio",
                    "exec_fitness_caption",
                    default=(
                        "적합도%=Soft·논리·해부·타이밍 가중합 · "
                        "≥80 강권고 · 50–79 조건부 · <50 보류 · "
                        "오늘%=슬라이드 · Soft점수 비가산 · target 불변"
                    ),
                )
            )
        return
        flow_data_dir = Path(
            getattr(ctx, "source_data_dir", None) or (Path(ctx.root) / "data")
        )
        try:
            chart_map = reads_by_ticker(ctx)
        except Exception:  # noqa: BLE001
            chart_map = {}
        pairs = build_weight_actions_for_rows(
            rows, chart_map=chart_map, flow_data_dir=flow_data_dir
        )
        board_acts = set(board_items(pairs))
        actionable = [
            (r, a)
            for r, a in pairs
            if a in board_acts or a.stance == "매수"
        ]
        if not actionable:
            actionable = [(r, a) for r, a in pairs if a.priority < 100]
        maps = _exec_fitness_maps(ctx)
        fit_rows = build_fitness_board_rows(actionable, **maps)
        st.markdown(exec_fitness_board_html(fit_rows), unsafe_allow_html=True)
        st.caption(
            copy_get(
                "portfolio",
                "exec_fitness_caption",
                default=(
                    "적합도%=Soft·논리·해부·타이밍 가중합 · "
                    "≥80 강권고 · 50–79 조건부 · <50 보류 · "
                    "오늘%=슬라이드 · Soft점수 비가산 · target 불변"
                ),
            )
        )
    except Exception:  # noqa: BLE001
        st.caption("집행 적합도 보드를 건너뜀 · 배지·집합으로 Review")


def _render_rank_hysteresis_board(ctx: DashboardContext) -> None:
    """미세 순위 변화 vs 교체 Review — Soft 제안 대비 점수 갭 시각화."""
    if is_short(getattr(ctx, "screen_horizon", None)):
        return
    try:
        from alpha_system.ui.services.rank_hysteresis import (
            build_rank_hysteresis_board,
            rank_hysteresis_board_html,
        )

        held = list(getattr(ctx, "ops_portfolio_rows", None) or [])
        prop = list(getattr(ctx, "portfolio_rows", None) or [])
        if not held:
            return
        board = build_rank_hysteresis_board(
            held,
            prop,
            root=Path(ctx.root),
        )
        st.markdown(rank_hysteresis_board_html(board), unsafe_allow_html=True)
        st.caption(
            copy_get(
                "portfolio",
                "rank_hysteresis_caption",
                default=(
                    "순위 안정: 갭≥20%·연속2회 전엔 유지 · "
                    "축소 스텝(줄이기/환금/전량)과 별축 · 전량교체 아님 · Review-only"
                ),
            )
        )
    except Exception:  # noqa: BLE001
        st.caption("순위 안정 보드를 건너뜀 · 보유·제안 대조로 Review")


def _render_weight_action_board(ctx: DashboardContext) -> None:
    """회차 슬라이드 — 평가액이 있을 때만. 티커만 등록이면 집합 보드만."""
    try:
        rows = list(getattr(ctx, "ops_portfolio_rows", None) or [])
        if not rows:
            return
        value_sum = 0.0
        for r in rows:
            try:
                value_sum += float(r.weight_pct or 0)
            except (TypeError, ValueError):
                pass
        # 멤버십만(평가액·비중 없음)이면 비중 보드 생략
        if value_sum < 0.5:
            st.caption(
                copy_get(
                    "portfolio",
                    "membership_only_caption",
                    default=(
                        "보유=티커만 등록됨 · 평단·% 없이 집합 대조로 Review · "
                        "회차 금액은 HTS"
                    ),
                )
            )
            return
        from alpha_system.ui.services.proposal_chart_board import reads_by_ticker
        from alpha_system.ui.services.weight_action import (
            board_items,
            build_weight_actions_for_rows,
            weight_action_board_html,
        )

        flow_data_dir = Path(
            getattr(ctx, "source_data_dir", None) or (Path(ctx.root) / "data")
        )
        try:
            chart_map = reads_by_ticker(ctx)
        except Exception:  # noqa: BLE001 — board must not break holdings
            chart_map = {}
        pairs = build_weight_actions_for_rows(
            rows,
            chart_map=chart_map,
            flow_data_dir=flow_data_dir,
        )
        from alpha_system.ui.services.today_port_projection import (
            port_weight_plan_html,
            project_portfolio_after_today,
        )

        with st.expander(
            copy_get(
                "portfolio",
                "today_weight_detail",
                default="회차 금액 참고 · 평가액 있을 때만",
            ),
            expanded=False,
        ):
            st.markdown(
                _fold_lead_html(
                    purpose=(
                        "종목 자리=100으로 둔 ‘오늘 얼마’ 참고표입니다. "
                        "계좌 전체 %를 맞추는 화면이 아닙니다."
                    ),
                    do_now=(
                        "축소 스텝=줄이기25·환금50·전량100(합산 아님·≠교체) · "
                        "매수≤33 · 재조회 전 당일 체결·미체결 차감 · HTS만."
                    ),
                    ignore="평단 필수 · target 자동 기입 · 포트 캡과 혼동",
                ),
                unsafe_allow_html=True,
            )
            proj = project_portfolio_after_today(
                rows,
                pairs=pairs,
                proposal=list(getattr(ctx, "portfolio_rows", None) or []),
            )
            st.markdown(port_weight_plan_html(proj), unsafe_allow_html=True)
            actionable = board_items(pairs)
            if actionable:
                st.markdown(
                    weight_action_board_html(actionable),
                    unsafe_allow_html=True,
                )
    except Exception:  # noqa: BLE001 — never blank the holdings book
        st.caption("회차 슬라이드를 건너뜀 · 집합 대조로 Review")


def _render_stance_decision(ctx: DashboardContext) -> None:
    """Momentum vs contrarian Soft — same axes as economy compass."""
    if is_short(getattr(ctx, "screen_horizon", None)):
        return
    try:
        from alpha_system.ui.services.stance_decision_board import (
            build_stance_decision_board,
            stance_decision_html,
        )

        board = build_stance_decision_board(Path(ctx.root))
        st.markdown(stance_decision_html(board), unsafe_allow_html=True)
        st.caption(
            copy_get(
                "portfolio",
                "stance_caption",
                default=(
                    "읽는 법: 위 행 ‘줄임/늘림’만 보면 됨 · "
                    "종목 배지(환금·트레일)가 더 강함 · target 불변"
                ),
            )
        )
    except Exception:  # noqa: BLE001
        st.caption("정발상·역발상 Soft를 건너뜀")


def _render_l3_history_review(ctx: DashboardContext) -> None:
    """L3·Fear Soft — 디스크 읽기 전용 · Shadow 재계산 때 갱신."""
    if is_short(getattr(ctx, "screen_horizon", None)):
        return
    import json

    market = str(getattr(ctx, "screen_market", None) or "KOSPI").upper()
    l3_path = Path(ctx.root) / "data" / "local" / f"l3_crash_review_{market}.json"
    fear_path = Path(ctx.root) / "data" / "local" / "fear_soft_review.json"
    with st.expander(
        copy_get(
            "portfolio",
            "l3_history_expand",
            default="급락 이력 · Shadow 때 갱신",
        ),
        expanded=False,
    ):
        st.markdown(
            _fold_lead_html(
                purpose="과거 급락·재진입 패턴 참고용입니다. 오늘 매매 순서를 바꾸지 않습니다.",
                do_now=(
                    copy_get(
                        "portfolio",
                        "l3_history_do_now",
                        default="백테스트「Shadow 다시 계산」으로 갱신 · 전량 강제·자동주문 없음.",
                    )
                ),
                ignore="결과로 target 기입 · Core 점수 변경",
            ),
            unsafe_allow_html=True,
        )
        if not l3_path.is_file() and not fear_path.is_file():
            st.caption(
                copy_get(
                    "portfolio",
                    "l3_history_idle",
                    default=(
                        "아직 이력 없음 · 백테스트에서 Shadow 다시 계산하면 "
                        "보유(+target) 기준으로 저장됩니다."
                    ),
                )
            )
            return
        try:
            from alpha_system.shadow.l3_crash_backtest import report_card_html
            from alpha_system.shadow.fear_soft_rebal_backtest import (
                fear_soft_card_html,
            )

            if l3_path.is_file():
                report = json.loads(l3_path.read_text(encoding="utf-8"))
                st.markdown(report_card_html(report), unsafe_allow_html=True)
            if fear_path.is_file():
                fg = json.loads(fear_path.read_text(encoding="utf-8"))
                st.markdown(fear_soft_card_html(fg), unsafe_allow_html=True)
        except Exception:  # noqa: BLE001
            st.caption("L3 이력 카드 렌더 실패")


def _render_shadow_profit_card(ctx: DashboardContext) -> None:
    """Mid shadow P&L card — Review-only, never writes target."""
    try:
        from alpha_system.shadow.mid_ledger import ledger_path, load_ledger
        from alpha_system.shadow.report import shadow_card_html, shadow_report_dict
        from alpha_system.shadow.run import run_shadow_day
    except Exception:  # noqa: BLE001 — optional module
        return

    market = getattr(ctx, "screen_market", None)
    root = Path(ctx.root)
    # Best-effort: append today's step if prices advanced (no-op if already recorded).
    try:
        # 후보(게이트 통과) + 제안 + 보유 → P1 풀 (목표가·가격은 행에 있을 때만 필터).
        cov_extra = []
        for sr in list(getattr(ctx, "scoreboard_rows", None) or []):
            elig = getattr(sr, "eligibility", None)
            if elig is False:
                continue
            cov_extra.append(
                {
                    "ticker": getattr(sr, "ticker", None),
                    "total_score": getattr(sr, "total_score", None),
                    "is_held": bool(getattr(sr, "is_held", False)),
                    "has_target": True,
                    "eligible": True,
                }
            )
        run_shadow_day(
            root,
            market=market,
            proposal_rows=list(getattr(ctx, "portfolio_rows", None) or []) + cov_extra,
            ops_rows=list(getattr(ctx, "ops_portfolio_rows", None) or []),
            persist=True,
        )
    except Exception:  # noqa: BLE001 — shadow must not break holdings UI
        pass
    try:
        rows = load_ledger(ledger_path(root, market))
        rotation_events = None
        try:
            from alpha_system.shadow.rotation_coverage import (
                load_rotation_events,
                rotation_log_path,
            )

            rotation_events = load_rotation_events(rotation_log_path(root, market))
        except Exception:  # noqa: BLE001
            rotation_events = None
        report = shadow_report_dict(rows, rotation_events=rotation_events)
        st.markdown(shadow_card_html(report), unsafe_allow_html=True)
        st.caption(
            copy_get(
                "portfolio",
                "shadow_profit_caption",
                default=(
                    "연습장 손익 · 실제 매매 지시 아님 · "
                    "곡선·KPI는 사이드바「백테스트」 · target 불변"
                ),
            )
        )
    except Exception:  # noqa: BLE001
        return


def _render_short_vol_budget_banner(ctx: DashboardContext) -> None:
    """Review-only: short sleeve budget card (not per-name weight)."""
    if not is_short(getattr(ctx, "screen_horizon", None)):
        return
    advice = getattr(ctx, "short_vol_budget", None)
    if advice is None:
        return

    level = str(getattr(advice, "level", "") or "") or "missing"
    as_of = str(getattr(advice, "as_of", "") or "")
    action = str(getattr(advice, "action", "") or "")
    scale = float(getattr(advice, "scale", 1.0) or 1.0)
    vix = getattr(advice, "vix", None)
    dd = getattr(advice, "kospi_dd_pct", None)

    level_label = {
        "calm": copy_get("portfolio", "short_vol_level_calm", default="평온"),
        "elevated": copy_get("portfolio", "short_vol_level_elevated", default="고변동"),
        "extreme": copy_get("portfolio", "short_vol_level_extreme", default="극단 변동"),
        "missing": copy_get("portfolio", "short_vol_level_missing", default="데이터없음"),
    }.get(level, level)

    tone = {
        "calm": "calm",
        "elevated": "elevated",
        "extreme": "extreme",
        "missing": "missing",
    }.get(level, "missing")

    scale_pct = int(round(scale * 100))
    if level == "calm":
        scale_line = copy_get(
            "portfolio",
            "short_vol_scale_full",
            default="평소 100%",
        )
        scale_sub = copy_get(
            "portfolio",
            "short_vol_scale_sub_ok",
            default="위성 예산 유지",
        )
    elif level == "missing":
        scale_line = "—"
        scale_sub = copy_get(
            "portfolio",
            "short_vol_scale_sub_na",
            default="권고 불가",
        )
    else:
        scale_line = f"{scale_pct}%"
        scale_sub = copy_get(
            "portfolio",
            "short_vol_scale_sub_cut",
            default="평소 대비 목표",
        )

    if not action:
        if level == "missing":
            action = copy_get(
                "portfolio",
                "short_vol_action_missing",
                default="시장 지표 갱신 후 재확인",
            )
        else:
            action = copy_get(
                "portfolio",
                "short_vol_action_ok",
                default="평소 단기 예산 유지 가능",
            )

    chips: list[str] = []
    if vix is not None:
        try:
            chips.append(f"VIX {float(vix):g}")
        except (TypeError, ValueError):
            pass
    if dd is not None:
        try:
            chips.append(f"코스피 고가대비 {float(dd):+.1f}%")
        except (TypeError, ValueError):
            pass
    if as_of:
        chips.append(f"as_of {as_of}")
    chips_html = (
        "".join(f'<span class="svb-chip">{_esc(c)}</span>' for c in chips)
        if chips
        else f'<span class="svb-chip">{_esc(copy_get("portfolio", "short_vol_chip_empty", default="지표 없음"))}</span>'
    )

    kicker = copy_get(
        "portfolio",
        "short_vol_kicker",
        default="단기 위성 예산",
    )
    do_lab = copy_get("portfolio", "short_vol_row_do", default="할 일")
    why_lab = copy_get("portfolio", "short_vol_row_why", default="근거")
    foot = copy_get(
        "portfolio",
        "short_vol_foot",
        default="종목당 비중·단기채 비율이 아님 · Review-only · 자동매도 없음",
    )

    html_block = (
        f'<div class="svb-card svb-card-{_esc(tone)}">'
        f'<div class="svb-kicker">{_esc(kicker)}</div>'
        f'<div class="svb-head">'
        f'<div class="svb-level">{_esc(level_label)}</div>'
        f'<div class="svb-scale-wrap">'
        f'<div class="svb-scale">{_esc(scale_line)}</div>'
        f'<span class="svb-scale-label">{_esc(scale_sub)}</span>'
        f"</div></div>"
        f'<div class="svb-row"><span class="svb-row-lab">{_esc(do_lab)}</span>'
        f"<div>{_esc(action)}</div></div>"
        f'<div class="svb-row"><span class="svb-row-lab">{_esc(why_lab)}</span>'
        f'<div class="svb-metrics">{chips_html}</div></div>'
        f'<div class="svb-foot">{_esc(foot)}</div>'
        f"</div>"
    )
    st.markdown(html_block, unsafe_allow_html=True)


def _render_monthly_rebal_note(ctx: DashboardContext) -> None:
    from alpha_system.ui.services.monthly_rebal_board import build_monthly_rebal_board

    board = build_monthly_rebal_board(ctx)
    if not board.do_now_count:
        return
    st.caption(
        copy_get(
            "portfolio",
            "rebal_note",
            default="월 리밸 참고 {n}건 — Review-only · target 자동기입 없음.",
            n=board.do_now_count,
        )
    )


def _current_alpha_paste(ctx: DashboardContext) -> str:
    from alpha_system.ui.services.holdings_input import (
        HoldingDraft,
        format_drafts_as_paste,
    )

    drafts: list[HoldingDraft] = []
    path = ctx.data_dir / "positions.csv"
    if path.exists():
        try:
            df = pd.read_csv(path, dtype=str)
            if not df.empty and "asset_group" in df.columns:
                kr = df[df["asset_group"].astype(str) == "kr_alpha"]
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
    if not drafts:
        for r in ctx.ops_portfolio_rows or []:
            drafts.append(
                HoldingDraft(
                    ticker=str(r.ticker).zfill(6),
                    quantity=0.0,
                    avg_price=r.avg_price,
                    name=str(r.name or ""),
                )
            )
    return format_drafts_as_paste(drafts)


def _saved_kr_alpha_rows(ctx: DashboardContext) -> list[dict[str, object]]:
    """Read kr_alpha rows from positions.csv (includes qty=0 placeholders)."""
    path = ctx.data_dir / "positions.csv"
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
        out.append({"ticker": tk, "name": str(row.get("name") or tk), "quantity": qty})
    return out


def _persist_watch_holdings(ctx: DashboardContext, tickers: list[str]) -> None:
    from alpha_system.ui.services.holdings_input import (
        drafts_from_tickers,
        upsert_kr_alpha_positions,
    )

    drafts = drafts_from_tickers(tickers, root=ctx.root)
    path = ctx.data_dir / "positions.csv"
    upsert_kr_alpha_positions(
        path,
        drafts,
        root=ctx.root,
        replace_alpha=True,
        keep_zero_qty=True,
        keep_existing_meta=True,
    )
    st.session_state["holdings_input_open"] = True
    st.session_state[f"holdings_paste_pending_{_book_keys(ctx)}"] = (
        _current_alpha_paste(ctx)
    )


def _render_holdings_one_click(
    ctx: DashboardContext,
    *,
    soft_tickers: list[str],
    deep_tickers: list[str],
    held_tickers: list[str],
) -> None:
    """Soft∪심층 미보유 → positions kr_alpha 합치기 · Soft·target 불변."""
    from alpha_system.proposal_chart import norm_ticker
    from alpha_system.ui.services.holdings_input import merge_kr_alpha_tickers

    held = {
        norm_ticker(t)
        for t in (held_tickers or [])
        if norm_ticker(t) and norm_ticker(t) != "000000"
    }
    pool: list[str] = []
    seen: set[str] = set()
    for raw in list(soft_tickers or []) + list(deep_tickers or []):
        tk = norm_ticker(raw)
        if not tk or tk == "000000" or tk in seen:
            continue
        seen.add(tk)
        pool.append(tk)
    missing = [t for t in pool if t not in held]
    n_soft_miss = sum(
        1
        for t in soft_tickers or []
        if norm_ticker(t) and norm_ticker(t) not in held
    )
    n_deep_miss = sum(
        1
        for t in deep_tickers or []
        if norm_ticker(t) and norm_ticker(t) not in held
    )
    label = copy_get(
        "portfolio",
        "holdings_one_click",
        default="미보유 Soft·심층 → 보유 등록 ({n})",
        n=len(missing),
    )
    st.caption(
        copy_get(
            "portfolio",
            "holdings_one_click_cap",
            default=(
                "원버튼 · Soft미보유 {s} · 심층미보유 {d} · "
                "기존 수량·평단 유지 · Soft·target·자동매수 없음"
            ),
            s=n_soft_miss,
            d=n_deep_miss,
        )
    )
    if st.button(
        label,
        key=f"holdings_one_click_{_book_keys(ctx)}",
        use_container_width=True,
        disabled=not missing,
        help="L4 · Soft∪심층 미보유만 positions 합침 · Soft·target·자동매수 없음",
    ):
        res = merge_kr_alpha_tickers(
            Path(ctx.data_dir) / "positions.csv",
            missing,
            root=Path(ctx.root),
        )
        added = list(res.get("added") or [])
        st.success(
            copy_get(
                "portfolio",
                "holdings_one_click_ok",
                default="보유 등록 {n}종 · 이미 있음 {s} · 자동매수 없음",
                n=len(added),
                s=len(res.get("skipped_existing") or []),
            )
        )
        st.session_state["holdings_input_open"] = True
        st.rerun()


def _extra_by_ticker(ctx: DashboardContext) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in list(ctx.portfolio_rows or []) + list(
        getattr(ctx, "proposal_blocked_rows", None) or []
    ) + list(ctx.ops_portfolio_rows or []):
        tk = str(row.ticker).zfill(6)
        extra = dict(row.extra or {})
        if getattr(row, "target_price", None) is not None:
            extra.setdefault("target_price", row.target_price)
        out[tk] = extra
    return out


def _style_watch_df(frame: pd.DataFrame):
    from alpha_system.ui.theme_prefs import normalize_theme, watch_row_styles

    theme = normalize_theme(st.session_state.get("saa_ui_theme") or "dark")
    tones = watch_row_styles(theme)

    def _hl(row: pd.Series) -> list[str]:
        css = tones.get(str(row.get("구분") or ""), "")
        return [css] * len(row)

    return frame.style.apply(_hl, axis=1)


def _watch_hakedaka_by_ticker(
    ctx: DashboardContext, tickers: list[str]
) -> dict[str, str]:
    """Gate summary for the observation table. Not score_sr / not a 0–100 score."""
    from alpha_system.sizing.hakedaka_screen import (
        evaluate_hakedaka,
        hits_label_short,
        load_hakedaka_inputs,
    )

    if is_short(getattr(ctx, "screen_horizon", None)):
        return {str(t).zfill(6) if str(t).isdigit() else str(t): "단기 미적용" for t in tickers}
    if not bool(getattr(ctx.cfg.sizing, "hakedaka_gate_enabled", True)):
        return {str(t).zfill(6) if str(t).isdigit() else str(t): "게이트 off" for t in tickers}

    book = _source_dir(ctx)
    inputs = load_hakedaka_inputs(ctx.root, data_dir=book)
    min_hits = int(getattr(ctx.cfg.sizing, "hakedaka_min_hits", 2) or 2)
    out: dict[str, str] = {}
    for raw in tickers:
        tk = str(raw).zfill(6) if str(raw).isdigit() else str(raw)
        out[tk] = hits_label_short(evaluate_hakedaka(tk, inputs, min_hits=min_hits))
    return out


def _watch_eval_enrichment(
    ctx: DashboardContext, tickers: list[str]
) -> dict[str, dict[str, str]]:
    """판정·심층·공시 from disk caches only (no network)."""
    from alpha_system.review.screen_deep_verify import load_screen_verify
    from alpha_system.sizing.qual_overlay import load_qual_overlay, overlay_path
    from alpha_system.ui.services.cecs_opendart_pack import load_opendart_watch
    from alpha_system.ui.services.opendart_evidence_board import (
        build_watch_eval_map,
        parse_evidence_board,
    )

    data_dir = Path(_source_dir(ctx))
    try:
        sv_board = load_screen_verify(data_dir)
        sv_rows = list(sv_board.rows)
    except Exception:  # noqa: BLE001
        sv_rows = []
    flags: list = []
    evidence: list = []
    try:
        snap = load_opendart_watch(ctx.root, data_dir=data_dir)
        if snap is not None:
            flags = list(snap.flag_models())
            evidence = parse_evidence_board(getattr(snap, "evidence", None) or [])
    except Exception:  # noqa: BLE001
        pass
    gated: set[str] = set()
    try:
        gated = set(load_qual_overlay(overlay_path(data_dir)).gated_tickers())
    except Exception:  # noqa: BLE001
        gated = set()
    return build_watch_eval_map(
        tickers,
        screen_verify_rows=sv_rows,
        board=evidence,
        flags=flags,
        gated=gated,
    )


def _proposal_weight_by_ticker(ctx: DashboardContext) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in list(ctx.portfolio_rows or []):
        tk = str(getattr(r, "ticker", "") or "")
        if tk.isdigit():
            tk = tk.zfill(6)
        if tk:
            try:
                out[tk] = float(r.weight_pct)
            except (TypeError, ValueError):
                continue
    return out


def _render_watch_pool(
    ctx: DashboardContext,
    preview_cutoff: float | None,
    preview_n: int,
) -> None:
    watch_key, watch_sig, watch_last = _watch_session_keys(ctx)
    saved = _saved_kr_alpha_rows(ctx)
    saved_tickers = {str(r["ticker"]) for r in saved}
    proposal_tickers = {str(r.ticker).zfill(6) for r in (ctx.portfolio_rows or [])}
    blocked_tickers = {
        str(r.ticker).zfill(6)
        for r in (getattr(ctx, "proposal_blocked_rows", None) or [])
    }
    board = build_rank_watchboard(
        ctx.scoreboard_rows or [],
        proposal_tickers=proposal_tickers,
        held_tickers=saved_tickers,
        proposal_band_max=int(preview_n),
        max_rows=watch_max(
            getattr(ctx, "screen_market", None),
            getattr(ctx, "screen_horizon", None),
        ),
    )
    metrics = load_watch_metrics(ctx.root, data_dir=_source_dir(ctx))
    hk_map = _watch_hakedaka_by_ticker(ctx, [r.ticker for r in board.rows])
    table_rows = build_watch_table_rows(
        board,
        metrics=metrics,
        extra_by_ticker=_extra_by_ticker(ctx),
        sector_labels=load_sector_labels(ctx.root),
        cutoff=preview_cutoff,
        target_n=int(preview_n),
        blocked_tickers=blocked_tickers,
        hakedaka_by_ticker=hk_map,
    )
    watch_tickers = [r.ticker for r in board.rows]
    regime_board = build_sector_regime_board(
        ctx.scoreboard_rows or [],
        root=ctx.root,
        data_dir=_source_dir(ctx),
        held_tickers=list(saved_tickers),
        proposal_tickers=list(proposal_tickers),
        watch_tickers=watch_tickers,
        tickers_for_chips=watch_tickers,
        include_complements=False,
    )

    short_watch = is_short(getattr(ctx, "screen_horizon", None))
    with st.container(border=True):
        legend = (
            '<div class="pf-watch-legend">'
            '<span><span class="pf-swatch pf-swatch-proposal"></span>'
            f"{copy_get('portfolio', 'watch_legend_proposal', default='최종 제안')}</span>"
            '<span><span class="pf-swatch pf-swatch-eligible"></span>'
            f"{copy_get('portfolio', 'watch_legend_eligible', default='컷 통과')}</span>"
            '<span><span class="pf-swatch pf-swatch-blocked"></span>'
            f"{copy_get('portfolio', 'watch_legend_blocked', default='편입 제외')}</span>"
            '<span><span class="pf-swatch pf-swatch-watch"></span>'
            f"{copy_get('portfolio', 'watch_legend_watch', default='관찰')}</span>"
            "</div>"
        )
        regime_chips: list[tuple[str, str]] = [
            ("평가 통합 표", "ok"),
            ("「보유」→ ④", "ok"),
            (
                copy_get(
                    "portfolio",
                    "regime_fit_chip",
                    default="국면적합 Review",
                ),
                "ok",
            ),
        ]
        if regime_board.stage is not None:
            stage_txt = (
                f"{regime_board.stage}단계"
                + (f" · {regime_board.stage_label}" if regime_board.stage_label else "")
            )
            regime_chips.append((stage_txt, "ok"))
        _render_section_head(
            copy_get("portfolio", "sec_watch", default="② 후보"),
            summary=copy_get(
                "portfolio",
                "watch_intro_short" if short_watch else "watch_intro",
                default=(
                    "한 표=점수·판정·심층·공시·하케다카 · 행 색=③ 관계 · 「보유」=④."
                    if short_watch
                    else (
                        "한 표에 점수·판정·심층·공시·하케다카·가격을 모음 · "
                        "행 색=최종 제안/컷 통과/편입 제외 · 「보유」체크=④ 실보유."
                    )
                ),
            ),
            chips=regime_chips,
            extra_html=legend,
            tier="primary",
        )
        if board.warnings:
            for w in board.warnings:
                st.caption(w)
        if getattr(board, "proposal_outside", ()):
            po = " · ".join(
                f"{r.name} ({r.ticker}) {r.rank}위" for r in board.proposal_outside
            )
            st.info(
                f"최종 Soft 제안이 점수순 관찰 "
                f"{watch_max(getattr(ctx, 'screen_market', None), getattr(ctx, 'screen_horizon', None))} "
                f"밖이라 표에 강제 포함: {po}. "
                "관찰=전 종목 점수순 · Soft=적격+Lab Soft만 (집합이 다를 수 있음)."
            )
        if board.held_outside:
            outside = " · ".join(
                f"{r.name} ({r.ticker}) {r.rank}위" for r in board.held_outside
            )
            st.warning(
                f"관찰 {watch_max(getattr(ctx, 'screen_market', None), getattr(ctx, 'screen_horizon', None))} 밖 — "
                f"잔류하지 않음: {outside}. "
                "표에서 체크를 바꾸면 알파에서 빠집니다."
            )
        if not table_rows:
            st.info("스크린된 관찰 종목이 없습니다. 점수판·컷오프를 확인하세요.")
        else:
            records = []
            short = is_short(getattr(ctx, "screen_horizon", None))
            absorb_map = {}
            if short:
                from alpha_system.ui.services.short_absorb_signal import (
                    absorb_label_for_ticker,
                    build_absorb_map,
                )

                absorb_map = build_absorb_map(
                    ctx.root, getattr(ctx, "screen_market", None)
                )
            eval_map = _watch_eval_enrichment(
                ctx, [r.ticker for r in table_rows]
            )
            weight_map = _proposal_weight_by_ticker(ctx)
            for r in table_rows:
                tk = str(r.ticker).zfill(6) if str(r.ticker).isdigit() else str(r.ticker)
                ev = eval_map.get(tk) or {}
                w = weight_map.get(tk)
                fit_lbl = fit_label_for_ticker(regime_board, r.ticker)
                fit_why = fit_why_for_ticker(regime_board, r.ticker)
                rec = {
                    "보유": r.ticker in saved_tickers,
                    "순위": r.rank,
                    "구분": watch_tone_label(r.tone),
                    "국면적합": fit_lbl,
                    "종목": r.name,
                    "차트": naver_fchart_url(r.ticker),
                    "코드": r.ticker,
                    "점수": r.total_score,
                    "SR": r.score_sr,
                    "판정": ev.get("판정") or "—",
                    "심층": ev.get("심층") or "—",
                    "공시": ev.get("공시") or "—",
                    "하케다카": r.hakedaka or "—",
                    "제안%": round(w, 1) if w is not None else None,
                    "배당%": r.dividend_yield,
                    "섹터": r.sector or "—",
                    "국면why": fit_why or "—",
                    "PER": r.per,
                    "PBR": r.pbr,
                    "ROE": r.roe,
                    "현재가": r.current_price,
                    "목표가": r.target_price,
                }
                if short:
                    rec["흡수"] = absorb_label_for_ticker(absorb_map, r.ticker)
                records.append(rec)
            frame = pd.DataFrame.from_records(records)
            saved_in_30 = tuple(
                sorted(r.ticker for r in table_rows if r.ticker in saved_tickers)
            )
            sig = tuple(r.ticker for r in table_rows)
            if st.session_state.get(watch_sig) != sig:
                st.session_state.pop(watch_key, None)
                st.session_state[watch_sig] = sig
                st.session_state[watch_last] = saved_in_30

            # 「보유」체크 + 구분 행 색 · 좁은 창은 가로 스크롤(깨짐 방지).
            locked_cols = [c for c in frame.columns if c != "보유"]
            core_cols = [
                "보유",
                "순위",
                "구분",
                "국면적합",
                "종목",
                "차트",
                "점수",
                "SR",
                "판정",
                "심층",
                "공시",
                "하케다카",
                "제안%",
                "현재가",
                "목표가",
            ]
            extra_cols = [
                c
                for c in (
                    "코드",
                    "배당%",
                    "섹터",
                    "국면why",
                    "PER",
                    "PBR",
                    "ROE",
                    "흡수",
                )
                if c in frame.columns
            ]
            compact = st.toggle(
                copy_get(
                    "portfolio",
                    "watch_compact_cols",
                    default="핵심 열만 (좁은 창)",
                ),
                value=False,
                key=f"{watch_key}_compact",
                help="켜면 차트·코드·PER 등을 숨기고 평가 열을 남깁니다. 끄면 가로 스크롤.",
            )
            show_cols = [c for c in core_cols if c in frame.columns]
            if not compact:
                show_cols = show_cols + [c for c in extra_cols if c not in show_cols]
            # Keep any unexpected columns at the end when not compact.
            if not compact:
                show_cols = show_cols + [
                    c for c in frame.columns if c not in show_cols
                ]
            st.markdown('<div class="pf-watch-scroll">', unsafe_allow_html=True)
            edited = st.data_editor(
                _style_watch_df(frame),
                hide_index=True,
                width="stretch",
                height=38 + 33 * len(frame),
                row_height=32,
                disabled=locked_cols,
                column_order=show_cols,
                key=watch_key,
                placeholder="—",
                column_config={
                    "보유": st.column_config.CheckboxColumn(
                        "보유",
                        help="체크 = ④ 실보유 등록 · 바로 저장 · 자동매매 없음",
                        default=False,
                        width="small",
                    ),
                    "구분": st.column_config.TextColumn(
                        "구분",
                        help="행 색과 동일 · 최종 제안=녹 · 컷 통과=주황 · 편입 제외=적 · 관찰=기본",
                        width="small",
                    ),
                    "국면적합": st.column_config.TextColumn(
                        "국면적합",
                        help=(
                            copy_get(
                                "portfolio",
                                "regime_fit_help",
                                default=(
                                    "경제 나침반 국면×업종 Review · 유리/중립/불리/보류 · "
                                    "QVM 점수·순위·target 불변"
                                ),
                            )
                        ),
                        width="small",
                    ),
                    "국면why": st.column_config.TextColumn(
                        "국면why",
                        help="국면적합 한 줄 근거 · Review-only",
                        width="medium",
                    ),
                    "순위": st.column_config.NumberColumn(
                        "순위", format="%d", width="small"
                    ),
                    "종목": st.column_config.TextColumn("종목", width="medium"),
                    "차트": st.column_config.LinkColumn(
                        "차트",
                        help="네이버 일봉 차트",
                        display_text="차트",
                        width="small",
                    ),
                    "코드": st.column_config.TextColumn("코드", width="small"),
                    "점수": st.column_config.NumberColumn(
                        "점수", format="%.2f", width="small"
                    ),
                    "SR": st.column_config.NumberColumn(
                        "SR",
                        format="%.1f",
                        help="환원 score_sr (배당·성향·자사주·연속성) · 합계 25%",
                        width="small",
                    ),
                    "판정": st.column_config.TextColumn(
                        "판정",
                        help="스크린 심층 Review · 통과/보류/제외검토 · 점수·target 불변",
                        width="small",
                    ),
                    "심층": st.column_config.TextColumn(
                        "심층",
                        help="자동 심층 사유 · 사람만 편입·주문",
                        width="medium",
                    ),
                    "공시": st.column_config.TextColumn(
                        "공시",
                        help="OpenDART 가치실현·게이트 요약 · 캐시 기준",
                        width="medium",
                    ),
                    "제안%": st.column_config.NumberColumn(
                        "제안%",
                        format="%.1f",
                        help="③ 최종 제안 비중(%) · 없으면 빈칸",
                        width="small",
                    ),
                    "배당%": st.column_config.NumberColumn(
                        "배당%",
                        format="%.2f",
                        help="배당수익률(%) · 후보 30 안에서만 표시",
                        width="small",
                    ),
                    "하케다카": st.column_config.TextColumn(
                        "하케다카",
                        help=(
                            "순차 게이트 · 절대 4축(순현금·자사주·최대주주·순환출자). "
                            "예: 2/4 통과 · 미측정 1 = 충족 2, 미측정 1, 나머지 불충족. "
                            "×는 ‘측정됐는데 아님’ · 미측정과 다름. "
                            "합계·환원(score_sr)과 별개 · 단기 북은 미적용."
                        ),
                        width="small",
                    ),
                    "섹터": st.column_config.TextColumn("섹터", width="small"),
                    "흡수": st.column_config.TextColumn(
                        "흡수",
                        help=(
                            "단기 Review · 거래대금≥20일평균 3배 and 1M 수익률≤+3% "
                            "(급락 −20% 미만 제외). 매집 단정 아님 · 자동매수 없음."
                        ),
                        width="small",
                    ),
                    "PER": st.column_config.NumberColumn(
                        "PER", format="%.2f", width="small"
                    ),
                    "PBR": st.column_config.NumberColumn(
                        "PBR", format="%.2f", width="small"
                    ),
                    "ROE": st.column_config.NumberColumn(
                        "ROE", format="%.1f", width="small"
                    ),
                    "현재가": st.column_config.NumberColumn(
                        "현재가", format="%.0f", width="small"
                    ),
                    "목표가": st.column_config.NumberColumn(
                        "목표가", format="%.0f", width="small"
                    ),
                },
            )
            st.markdown("</div>", unsafe_allow_html=True)
            st.caption(
                copy_get(
                    "portfolio",
                    "watch_hakedaka_caption",
                    default=(
                        "하케다카 = 게이트 · 절대 /4 · SR·배당% = 환원 참고(점수 혼합 아님) · "
                        "미달이면 중기 최종 제안에서 제외될 수 있음 · "
                        "순환출자는 True만 측정(대부분 미측정이 정상)"
                    ),
                )
            )
            st.caption(
                copy_get(
                    "portfolio",
                    "regime_fit_caption",
                    default=(
                        "국면적합 = 나침반 stage×업종 Review · 점수 가산 없음 · "
                        "target 자동기입 없음 · 맵은 alpha_system/config/sector_regime_fit.yaml"
                    ),
                )
            )
            from alpha_system.sizing.hakedaka_screen import (
                coverage_for_tickers,
                load_hakedaka_inputs,
            )

            cov = coverage_for_tickers(
                [r.ticker for r in board.rows],
                load_hakedaka_inputs(ctx.root, data_dir=_source_dir(ctx)),
                min_hits=int(getattr(ctx.cfg.sizing, "hakedaka_min_hits", 2) or 2),
            )
            st.caption(cov.caption())
            if cov.n and cov.owner == 0:
                st.caption(
                    copy_get(
                        "portfolio",
                        "watch_hakedaka_owner_gap",
                        default=(
                            "최대주주 0% — OpenDART「다시 탐색」으로 관찰 풀만 보강 "
                            "(corp 코드 캐시·API). 전 유니버스가 아님."
                        ),
                    )
                )
            hold_flags = _watch_hold_flags(edited, n=len(table_rows))
            sel_tickers = [
                table_rows[i].ticker
                for i, on in enumerate(hold_flags)
                if on
            ]
            current = tuple(sorted(sel_tickers))
            prev = st.session_state.get(watch_last)
            if prev is None:
                st.session_state[watch_last] = saved_in_30
            elif current != prev:
                _persist_watch_holdings(ctx, list(current))
                st.session_state[watch_last] = current
                st.session_state.pop(watch_key, None)
                st.rerun()

        _render_candidate_ai_export(
            ctx,
            table_rows,
            preview_cutoff=preview_cutoff,
            preview_n=int(preview_n),
        )
        _render_holdings_paste(ctx)


def _render_candidate_ai_export(
    ctx: DashboardContext,
    table_rows,
    *,
    preview_cutoff: float | None,
    preview_n: int,
) -> None:
    pack = build_candidate_ai_export(
        market=getattr(ctx, "screen_market", "KOSPI"),
        as_of=ctx.as_of,
        cutoff=preview_cutoff,
        quality_min=getattr(ctx.cfg.scoring, "quality_min_score", None),
        target_n=int(preview_n),
        table_rows=table_rows,
        scoreboard_rows=ctx.scoreboard_rows or [],
        root=ctx.root,
        data_dir=_source_dir(ctx),
        hakedaka_min_hits=int(getattr(ctx.cfg.sizing, "hakedaka_min_hits", 2) or 2),
    )
    bk = _book_keys(ctx)
    with st.expander(
        copy_get("portfolio", "watch_ai_export_expand", default="다른 AI에 붙여넣기"),
        expanded=False,
    ):
        st.caption(
            copy_get(
                "portfolio",
                "watch_ai_export",
                default=(
                    "관찰 풀·점수·현재가·목표가를 Markdown/JSON으로 내려 "
                    "다른 AI에 붙입니다. target 파일·자동매매 없음."
                ),
            )
        )
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "Markdown 저장",
                data=pack.markdown.encode("utf-8"),
                file_name=f"{pack.file_stem}.md",
                mime="text/markdown; charset=utf-8",
                use_container_width=True,
                key=f"pf_ai_export_md_{bk}",
            )
        with c2:
            st.download_button(
                "JSON 저장",
                data=pack.json_text.encode("utf-8"),
                file_name=f"{pack.file_stem}.json",
                mime="application/json; charset=utf-8",
                use_container_width=True,
                key=f"pf_ai_export_json_{bk}",
            )
        st.code(pack.markdown, language="markdown")


def _render_holdings_paste(ctx: DashboardContext) -> None:
    from alpha_system.ui.services.holdings_input import (
        parse_holdings_paste,
        upsert_kr_alpha_positions,
    )

    bk = _book_keys(ctx)
    paste_key = f"holdings_paste_text_{bk}"
    pending_key = f"holdings_paste_pending_{bk}"
    pending = st.session_state.pop(pending_key, None)
    if pending is None:
        # legacy single-key bridge (중기만 있던 시절)
        pending = st.session_state.pop("holdings_paste_pending", None)
    if pending is not None:
        st.session_state[paste_key] = pending
    elif paste_key not in st.session_state:
        if "holdings_paste_text" in st.session_state and "mid" in bk:
            st.session_state[paste_key] = st.session_state.get("holdings_paste_text")
        else:
            st.session_state[paste_key] = _current_alpha_paste(ctx)

    with st.expander(
        copy_get(
            "portfolio",
            "holdings_paste_title",
            default="보유 티커 붙이기 · 집합 대조용",
        ),
        expanded=False,
    ):
        st.markdown(
            _fold_lead_html(
                purpose=(
                    "지금 들고 있는 종목코드를 등록해 "
                    "위「둘 다·제안만·보유만」대조에 쓰입니다."
                ),
                do_now="한 줄에 6자리 코드만 넣어도 됨 · 저장 후 집합 다시 확인.",
                ignore="평단·수량 필수 · 여기 붙인다고 자동매수",
            ),
            unsafe_allow_html=True,
        )
        text = st.text_area(
            "보유 목록",
            key=paste_key,
            height=140,
            placeholder="005930\n000660\n035420\n# 또는 005930 100 45000",
            label_visibility="collapsed",
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "티커 저장",
                type="primary",
                key=f"holdings_save_{bk}",
                use_container_width=True,
            ):
                parsed = parse_holdings_paste(text)
                if parsed.errors and not parsed.drafts:
                    for e in parsed.errors:
                        st.error(e)
                else:
                    for e in parsed.errors:
                        st.warning(e)
                    path = ctx.data_dir / "positions.csv"
                    membership_only = any(d.quantity <= 0 for d in parsed.drafts)
                    result = upsert_kr_alpha_positions(
                        path,
                        parsed.drafts,
                        root=ctx.root,
                        replace_alpha=True,
                        keep_zero_qty=membership_only,
                    )
                    saved_tks = [d.ticker for d in parsed.drafts]
                    _reset_watch_picker(ctx, saved_tks)
                    st.session_state["holdings_input_open"] = True
                    st.session_state[pending_key] = format_drafts_helper(
                        parsed.drafts
                    )
                    st.success(
                        f"알파 {result['alpha_count']}종 저장 · "
                        f"기타 {result['kept_other']}행 유지"
                    )
                    st.rerun()
        with c2:
            if st.button(
                "알파 비우기",
                key=f"holdings_clear_alpha_{bk}",
                use_container_width=True,
            ):
                path = ctx.data_dir / "positions.csv"
                upsert_kr_alpha_positions(
                    path, [], root=ctx.root, replace_alpha=True
                )
                _reset_watch_picker(ctx, [])
                st.session_state[pending_key] = ""
                st.session_state["holdings_input_open"] = True
                st.rerun()
        preview = parse_holdings_paste(
            st.session_state.get(paste_key) or ""
        )
        if preview.drafts:
            st.caption(
                f"인식 {len(preview.drafts)}종"
                + (f" · 경고 {len(preview.errors)}" if preview.errors else "")
            )


def format_drafts_helper(drafts) -> str:
    from alpha_system.ui.services.holdings_input import format_drafts_as_paste

    return format_drafts_as_paste(drafts)


def _render_sector_exposure(ctx: DashboardContext) -> None:
    from alpha_system.ui.services.sector_exposure import assess_sector_weight_caps

    rows = ctx.portfolio_rows or []
    if not rows:
        return
    exposures = assess_sector_weight_caps(rows, data_dir=_source_dir(ctx))
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
        return


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


def _render_cutoff_bar(ctx: DashboardContext) -> tuple[float | None, int]:
    """Compact cutoff + book-size controls. YAML unchanged until confirm.

    Returns (preview_cutoff, preview_target_n) for table coloring.
    """
    scored = [
        {
            "ticker": row.ticker,
            "name": row.name,
            "total_score": row.total_score,
            "score_q": row.score_q,
        }
        for row in ctx.scoreboard_rows
        if row.total_score is not None
    ]
    ladder = build_relative_cutoff_ladder(scored, min_rank=1)
    current_n = int(ctx.cfg.sizing.target_names)
    current_cutoff = ctx.cfg.scoring.score_cutoff
    rec = recommended_absolute_cutoff_option(ladder, scored)

    yaml_n = current_n
    n_min, n_max, n_default = target_names_band(
        getattr(ctx, "screen_market", None),
        getattr(ctx, "screen_horizon", None),
    )
    if yaml_n < n_min or yaml_n > n_max:
        yaml_n = n_default

    mkt = _book_keys(ctx)
    cutoff_key = f"portfolio_cutoff_natural_break_{mkt}"
    count_key = f"portfolio_target_names_band_{mkt}"

    with st.container(border=True):
        yaml_label = (
            f"{current_cutoff:.2f}" if current_cutoff is not None else "미확정"
        )
        _render_section_head(
            copy_get("portfolio", "sec_cutoff", default="① 선정 규칙"),
            summary=copy_get(
                "portfolio",
                "cutoff_caption",
                default="합격선·편입 수를 고른 뒤 아래에서 확정. 확정 전 YAML·제안 북은 그대로.",
            ),
            chips=[
                (f"저장 컷 {yaml_label}", "muted"),
                (f"편입 {current_n}종", "muted"),
            ],
            tier="input",
        )
        if not ladder or rec is None:
            _render_status_card(
                "컷오프를 계산할 유효 스코어가 없습니다. 확인 → ① 정량을 갱신하세요.",
                tone="warn",
            )
            return current_cutoff, yaml_n

        natural = [option for option in ladder if option.is_natural_break]
        if rec not in natural:
            natural = [rec, *natural]
        by_rank = {option.rank_n: option for option in natural}
        break_ranks = [option.rank_n for option in natural]

        def _session_rank(key: str, allowed) -> int | None:
            raw = st.session_state.get(key)
            try:
                value = int(raw)
            except (TypeError, ValueError):
                return None
            if value in allowed:
                return value
            return None

        if _session_rank(cutoff_key, by_rank) is None:
            matched = None
            if current_cutoff is not None:
                matched = next(
                    (
                        option
                        for option in natural
                        if abs(float(option.cutoff) - float(current_cutoff)) < 1e-6
                    ),
                    None,
                )
            st.session_state[cutoff_key] = (
                matched.rank_n if matched is not None else rec.rank_n
            )
        if _session_rank(count_key, set(range(n_min, n_max + 1))) is None:
            st.session_state[count_key] = yaml_n

        _render_control_card(
            "점수 컷오프",
            hint="합격선 · 아래 선택 · 표 색만 미리보기",
        )
        picked = st.radio(
            "점수 컷오프",
            options=break_ranks,
            format_func=lambda rank: (
                f"{by_rank[rank].cutoff:.2f} · 적격 {by_rank[rank].eligible_count}종"
                + (" · 권고" if rec is not None and rank == rec.rank_n else "")
            ),
            horizontal=True,
            key=cutoff_key,
            label_visibility="collapsed",
        )
        cutoff_opt = by_rank[int(picked)]
        _render_control_card(
            "제안 편입 수",
            hint="컷 통과 종목 중 제안에 담을 최대 수",
        )
        target_n = st.radio(
            "제안 편입 수",
            options=list(range(n_min, n_max + 1)),
            horizontal=True,
            key=count_key,
            label_visibility="collapsed",
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
            ctx.cfg.model_copy(
                update={
                    "scoring": ctx.cfg.scoring.model_copy(
                        update={"score_cutoff": cutoff_opt.cutoff}
                    ),
                    "sizing": ctx.cfg.sizing.model_copy(
                        update={"target_names": int(target_n)}
                    ),
                }
            ),
            tranche_id=TrancheId.T1,
            scores=preview_scores,
            existing_weights={},
            tranche_budget=1.0,
            overlay=load_qual_overlay(overlay_path(_source_dir(ctx))),
            exclude_tickers=collect_above_justified_target_tickers_from_root(
                [s.ticker for s in preview_scores],
                ctx.root,
            ),
        )
        selected_n = sum(
            1 for a in preview_alloc.allocated if a.incremental_weight > 0
        )
        _render_status_card(
            f"미리보기 컷 {cutoff_opt.cutoff:.2f} · 적격 {cutoff_opt.eligible_count}종 · "
            f"편입 {int(target_n)}종 · 제안 예상 {selected_n}종 "
            f"(저장 {yaml_label} / {current_n}종) · 확정 전 YAML·제안 북 불변",
            tone="ok",
        )

        changed = (
            current_n != int(target_n)
            or current_cutoff is None
            or abs(float(current_cutoff) - cutoff_opt.cutoff) > 1e-9
        )
        with st.expander("이 규칙으로 확정", expanded=current_cutoff is None):
            boundary = (
                f"경계 {cutoff_opt.boundary_ticker} {cutoff_opt.boundary_name}"
                + (
                    f" · 바로 아래 {cutoff_opt.next_ticker} "
                    f"{cutoff_opt.next_name} · 갭 {cutoff_opt.margin_below:.2f}"
                    if cutoff_opt.next_ticker is not None
                    and cutoff_opt.margin_below is not None
                    else ""
                )
            )
            _render_status_card(boundary, tone="muted")
            if not changed:
                st.success("현재 설정과 동일합니다.")
            else:
                confirm_1 = st.checkbox(
                    "절대 컷오프와 경계 종목을 확인했습니다",
                    key=f"portfolio_abs_cutoff_confirm_1_{mkt}",
                )
                confirm_2 = st.checkbox(
                    "확정 시 점수 컷오프·편입 종목 수가 바뀌고 제안 북이 재계산됨을 이해했습니다 "
                    "(목표 포트 파일은 변경되지 않음)",
                    key=f"portfolio_abs_cutoff_confirm_2_{mkt}",
                )
                if st.button(
                    "절대 컷오프·편입 수 최종 확정",
                    type="primary",
                    disabled=not (confirm_1 and confirm_2),
                    use_container_width=True,
                    key=f"portfolio_abs_cutoff_save_{mkt}",
                ):
                    try:
                        if is_short(getattr(ctx, "screen_horizon", None)):
                            backup = save_short_policy(
                                ctx.root,
                                getattr(ctx, "screen_market", None),
                                cutoff=cutoff_opt.cutoff,
                                target_names=int(target_n),
                            )
                        elif is_kosdaq(getattr(ctx, "screen_market", None)):
                            backup = save_kosdaq_policy(
                                ctx.root,
                                cutoff=cutoff_opt.cutoff,
                                target_names=int(target_n),
                            )
                        else:
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
                        proposal_tickers = [
                            str(a.ticker).zfill(6)
                            for a in preview_alloc.allocated
                            if float(a.incremental_weight) > 0
                        ]
                        if proposal_tickers:
                            try:
                                from alpha_system.ui.services.cecs_opendart_pack import (
                                    refresh_opendart_proposal_watch,
                                )

                                with st.spinner("확정된 제안 종목 OpenDART 탐색"):
                                    refresh_opendart_proposal_watch(
                                        ctx.root,
                                        proposal_tickers,
                                        as_of=ctx.as_of if isinstance(ctx.as_of, _date) else _date.today(),
                                        journal_path=ctx.root / "data" / "alpha_system_journal.jsonl",
                                    )
                            except Exception as exc:
                                st.warning(f"컷은 저장됨. OpenDART 탐색 실패: {exc}")
                        st.success(
                            f"cutoff {cutoff_opt.cutoff:.2f} / {int(target_n)}종 확정 · "
                            f"백업 `{backup.name}`"
                        )
                        st.rerun()

        return cutoff_opt.cutoff, int(target_n)
