"""Pack observation-pool candidates for paste into another AI.

Does not write target_portfolio.csv or change selection.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from alpha_system.product import PRODUCT_NAME, PRODUCT_TAGLINE
from alpha_system.screen_book import is_kosdaq, market_label, watch_max
from alpha_system.ui.services.context import ScoreboardRow
from alpha_system.ui.services.rank_watchboard import WatchTableRow, naver_fchart_url

_ROLLUP = (("품질", 35), ("가치", 30), ("환원", 25), ("리스크", 10))

_TSV_COLS = (
    "순위",
    "코드",
    "종목",
    "구분",
    "합계",
    "품질",
    "가치",
    "환원",
    "리스크",
    "섹터",
    "PER",
    "PBR",
    "ROE",
    "현재가",
    "목표가",
    "보유",
    "적격",
    "사유",
    "차트",
)


@dataclass(frozen=True)
class CandidateAiExport:
    markdown: str
    json_text: str
    file_stem: str
    n_watch: int


def _tk(raw: object) -> str:
    text = str(raw or "").strip()
    return text.zfill(6) if text.isdigit() else text


def _num(val: Optional[float], digits: int = 2) -> str:
    if val is None:
        return ""
    try:
        x = float(val)
    except (TypeError, ValueError):
        return ""
    if x != x:
        return ""
    if digits <= 0:
        return f"{int(round(x))}"
    text = f"{x:.{digits}f}".rstrip("0").rstrip(".")
    return text or "0"


def _json_num(val: Optional[float]) -> float | None:
    if val is None:
        return None
    try:
        x = float(val)
    except (TypeError, ValueError):
        return None
    if x != x:
        return None
    return x


def _elig_label(flag: Optional[bool]) -> str:
    if flag is True:
        return "예"
    if flag is False:
        return "아니오"
    return ""


def _score_map(rows: Sequence[ScoreboardRow]) -> dict[str, ScoreboardRow]:
    out: dict[str, ScoreboardRow] = {}
    for row in rows:
        out[_tk(row.ticker)] = row
    return out


def _watch_record(
    row: WatchTableRow,
    scored: Mapping[str, ScoreboardRow],
    *,
    hk_map: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    from alpha_system.sizing.cyclical_theme import is_cyclical_heavy

    tk = _tk(row.ticker)
    sc = scored.get(tk)
    reason = ""
    if sc is not None:
        reason = str(sc.eligibility_reason or "")
    digits = "".join(ch for ch in tk if ch.isdigit())
    cyclical = is_cyclical_heavy(
        sector=str(row.sector or ""),
        name=str(row.name or ""),
    )
    rec: dict[str, Any] = {
        "rank": int(row.rank),
        "ticker": tk,
        "name": str(row.name or tk),
        "tone": str(row.tone or ""),
        "total_score": _json_num(row.total_score),
        "score_q": _json_num(sc.score_q if sc is not None else None),
        "score_v": _json_num(sc.score_v if sc is not None else None),
        "score_sr": _json_num(sc.score_sr if sc is not None else None),
        "score_r": _json_num(sc.score_r if sc is not None else None),
        "sector": str(row.sector or ""),
        "per": _json_num(row.per),
        "pbr": _json_num(row.pbr),
        "roe": _json_num(row.roe),
        "current_price": _json_num(row.current_price),
        "target_price": _json_num(row.target_price),
        "held": bool(row.is_held),
        "eligible": None if row.eligibility is None else bool(row.eligibility),
        "eligibility_reason": reason,
        "chart": naver_fchart_url(tk) if digits else "",
        "cyclical_theme": cyclical,
    }
    hk = (hk_map or {}).get(tk)
    if hk is not None:
        rec["hakedaka_hits"] = int(getattr(hk, "hits", 0) or 0)
        rec["hakedaka_known"] = int(getattr(hk, "known", 0) or 0)
        rec["hakedaka_pass"] = bool(getattr(hk, "passed", True))
        rec["hakedaka_detail"] = str(getattr(hk, "detail", "") or "")
    return rec


def _tsv_line(rec: Mapping[str, Any]) -> str:
    cells = [
        str(rec.get("rank") or ""),
        str(rec.get("ticker") or ""),
        str(rec.get("name") or "").replace("\t", " "),
        str(rec.get("tone") or ""),
        _num(rec.get("total_score")),
        _num(rec.get("score_q")),
        _num(rec.get("score_v")),
        _num(rec.get("score_sr")),
        _num(rec.get("score_r")),
        str(rec.get("sector") or "").replace("\t", " "),
        _num(rec.get("per")),
        _num(rec.get("pbr"), 2),
        _num(rec.get("roe"), 1),
        _num(rec.get("current_price"), 0),
        _num(rec.get("target_price"), 0),
        "Y" if rec.get("held") else "",
        _elig_label(rec.get("eligible") if isinstance(rec.get("eligible"), bool) else None),
        str(rec.get("eligibility_reason") or "").replace("\t", " ").replace("\n", " "),
        str(rec.get("chart") or ""),
    ]
    return "\t".join(cells)


def _proposal_lines(records: Sequence[Mapping[str, Any]], *, tone: str = "제안") -> list[str]:
    picked = [r for r in records if str(r.get("tone") or "") == tone]
    if not picked:
        return ["(없음)"]
    lines = []
    for rec in picked:
        bits = [
            f"{rec.get('rank')}. {rec.get('name')} `{rec.get('ticker')}`",
            f"합계 {_num(rec.get('total_score'))}",
        ]
        if rec.get("eligible") is False:
            bits.append("부적격")
            if rec.get("eligibility_reason"):
                bits.append(str(rec["eligibility_reason"]))
        if rec.get("cyclical_theme"):
            bits.append("경기민감")
        if rec.get("hakedaka_detail"):
            bits.append(str(rec["hakedaka_detail"]))
        if rec.get("hakedaka_pass") is False:
            bits.append("하케다카 미달")
        lines.append(" · ".join(bits))
    return lines


def build_candidate_ai_export(
    *,
    market: object,
    as_of: date | str,
    cutoff: float | None,
    quality_min: float | None,
    target_n: int,
    table_rows: Sequence[WatchTableRow],
    scoreboard_rows: Sequence[ScoreboardRow] = (),
    root: Path | None = None,
    data_dir: Path | None = None,
    hakedaka_min_hits: int = 2,
) -> CandidateAiExport:
    """Markdown + JSON pack of the current observation pool. Read-only."""
    mkt = "KOSDAQ" if is_kosdaq(market) else "KOSPI"
    label = market_label(mkt)
    as_of_s = str(as_of)
    n_watch = watch_max(mkt)
    scored = _score_map(scoreboard_rows)
    hk_map: dict[str, Any] = {}
    if root is not None:
        from alpha_system.sizing.hakedaka_screen import (
            evaluate_hakedaka,
            load_hakedaka_inputs,
        )

        inputs = load_hakedaka_inputs(Path(root), data_dir=data_dir)
        for row in table_rows:
            tk = _tk(row.ticker)
            hk_map[tk] = evaluate_hakedaka(tk, inputs, min_hits=hakedaka_min_hits)
    records = [_watch_record(row, scored, hk_map=hk_map) for row in table_rows]
    payload = {
        "product": PRODUCT_NAME,
        "tagline": PRODUCT_TAGLINE,
        "market": mkt,
        "market_label": label,
        "as_of": as_of_s,
        "watch_max": n_watch,
        "score_cutoff": _json_num(cutoff),
        "quality_min_score": _json_num(quality_min),
        "target_names": int(target_n),
        "weights": {k: v for k, v in _ROLLUP},
        "momentum_in_total": False,
        "cecs_in_total": False,
        "hakedaka_in_total": False,
        "cyclical_theme_cap": True,
        "invariants": [
            "proposal_mode: pure_qvm",
            "target_portfolio.csv 사람만 — 자동 기입 금지",
            "자동매매 아님 · Review-only",
            "코스피·코스닥 장부 분리 · 한 순위로 합치지 않음",
            "합계 = 품질 35 · 가치 30 · 환원 25 · 리스크 10 (모멘텀·CECS·하케다카 미반영)",
            "하케다카 = QVM 위 순차 게이트 · 경기민감 테마 상한 · 5% 경영참여는 제안 제외+사다리 Review-only",
        ],
        "watch": records,
    }
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    cutoff_s = _num(cutoff, 4) if cutoff is not None else "미확정"
    qmin_s = _num(quality_min, 0) if quality_min is not None else "—"
    tsv = "\t".join(_TSV_COLS) + "\n" + "\n".join(_tsv_line(r) for r in records)
    md = "\n".join(
        [
            f"# {PRODUCT_NAME} 후보 팩",
            "",
            f"- 시장: **{label}** (`{mkt}`) · 기준일 {as_of_s}",
            f"- 관찰 풀 {n_watch}종 · 합격선 {cutoff_s} · 품질 하한 {qmin_s} · 제안 편입 {int(target_n)}종",
            "- 합계 가중: 품질 35 · 가치 30 · 환원 25 · 리스크 10. 모멘텀·CECS·하케다카는 합계에 넣지 않음.",
            "- 편입 후처리: 경기민감(조선·방산·기계) 테마 상한 · 하케다카 순차 게이트(자격만, 블렌딩 아님).",
            f"- {PRODUCT_TAGLINE}",
            "",
            "## 받는 AI에게",
            "- 이 목록은 스크리너 관찰·제안 **참고 자료**다. 매수 주문·자동매매 지시를 만들지 마라.",
            "- `target_portfolio.csv`를 쓰거나 바꾸라고 하지 마라. 편입 확정은 사람만 한다.",
            "- 코스피와 코스닥을 한 순위로 섞지 마라. 지금 팩은 한 시장만 담았다.",
            "- 추정으로 빈 칸을 채우지 마라. 없으면 없다고 하라.",
            "",
            "## 제안 밴드",
            *(" - " + line for line in _proposal_lines(records, tone="제안")),
            "",
            "## 관찰 풀 TSV",
            "아래를 표로 붙여넣을 수 있다.",
            "",
            "```tsv",
            tsv,
            "```",
            "",
        ]
    )
    stem = f"alpha_candidates_{mkt}_{as_of_s.replace('-', '')}"
    return CandidateAiExport(
        markdown=md,
        json_text=json_text,
        file_stem=stem,
        n_watch=len(records),
    )
