"""한국판 하케다카 · 고이즈미 노믹스 벤치 시나리오 Lab (Review-only).

일본 2001–06를 Soft 장부에 이식하지 않는다.
현재 Soft top · 행동주의 picks에 국면 배율(강/중/약)만 얹어
슬리브별 가상 Net·MDD 밴드를 남긴다.

불변: target · QVM 점수 · 자동주문 · Soft↔행동주의 점수 합산 금지.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from alpha_system.proposal_chart import norm_ticker

WRITES_TARGET = False
REVIEW_ONLY = True
OUT_REL = Path("data") / "local" / "koizumi_kr_hakedaka_scenario.json"

# 고이즈미 벤치 앵커(공개 요약 · 휴리스틱 — 예측 아님)
# 취임~2006중 TOPIX ≈+15~20% · 2003봄~05말 회복은 훨씬 큼 · 자사주 규제완화 2001
KOIZUMI_BENCH_NOTE = (
    "벤치=고이즈미 재임 TOPIX 대략 +15~20% · "
    "2003 이후 회복 구간은 더 큼 · 자사주 자유화 2001 · "
    "한국 배율은 유추 Soft Lab · 역사 복제 아님"
)

# 시나리오 총구간 가상 수익률(배수 아님 · 누적 ret) · MDD는 스트레스 하한
SCENARIOS: dict[str, dict[str, Any]] = {
    "weak": {
        "label_ko": "약 · 상법·자사주 반쪽 · 경기 역풍",
        "horizon_years": 3,
        "kospi_ret": -0.05,
        "soft_ret": 0.02,
        "activist_ret": 0.08,
        "mdd_soft": -0.22,
        "mdd_activist": -0.35,
        "mdd_blend": -0.28,
        "koizumi_map": "초기 부진·개혁 미흡에 가깝게",
    },
    "mid": {
        "label_ko": "중 · 고이즈미형 재임 성과 앵커",
        "horizon_years": 5,
        "kospi_ret": 0.20,
        "soft_ret": 0.28,
        "activist_ret": 0.55,
        "mdd_soft": -0.25,
        "mdd_activist": -0.40,
        "mdd_blend": -0.32,
        "koizumi_map": "재임 TOPIX≈+20% 앵커 · 지배구조·환매 프리미엄은 행동주의>",
    },
    "strong": {
        "label_ko": "강 · 2003–05형 강한 리레이트",
        "horizon_years": 5,
        "kospi_ret": 0.80,
        "soft_ret": 0.95,
        "activist_ret": 1.40,
        "mdd_soft": -0.28,
        "mdd_activist": -0.45,
        "mdd_blend": -0.35,
        "koizumi_map": "저점 이후 강한 회복 유추 · Soft도↑ · 테마가 더↑",
    },
}


@dataclass(frozen=True)
class BasketName:
    ticker: str
    name: str
    sleeve: str  # soft | activist
    weight_in_sleeve: float
    of_mid_soft_pct: float
    note: str = ""


@dataclass
class ScenarioBoard:
    as_of: str
    market: str
    soft_names: list[BasketName] = field(default_factory=list)
    activist_names: list[BasketName] = field(default_factory=list)
    scenarios: dict[str, dict[str, Any]] = field(default_factory=dict)
    soft_of_mid_pct: float = 50.0
    activist_of_mid_pct: float = 50.0
    review_only: bool = REVIEW_ONLY
    writes_target: bool = WRITES_TARGET
    bench_note: str = KOIZUMI_BENCH_NOTE
    limits: tuple[str, ...] = (
        "일본 구간 수익률을 종목에 붙여 넣지 않음",
        "QVM·target·자동주문 불변",
        "Soft·행동주의 점수 합산 금지 · 50/50 이원만",
        "vs 벤치는 휴리스틱 · Go-live·매수 신호 아님",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "market": self.market,
            "soft_of_mid_pct": self.soft_of_mid_pct,
            "activist_of_mid_pct": self.activist_of_mid_pct,
            "soft_names": [asdict(n) for n in self.soft_names],
            "activist_names": [asdict(n) for n in self.activist_names],
            "scenarios": self.scenarios,
            "bench_note": self.bench_note,
            "limits": list(self.limits),
            "review_only": self.review_only,
            "writes_target": self.writes_target,
        }


def _name_map(root: Path) -> dict[str, str]:
    path = root / "alpha_portfolio" / "data" / "output" / "alpha_scores.csv"
    if not path.is_file():
        return {}
    df = pd.read_csv(path, dtype=str)
    out: dict[str, str] = {}
    for _, row in df.iterrows():
        tk = norm_ticker(row.get("ticker"))
        if tk:
            out[tk] = str(row.get("name") or tk)
    return out


def load_soft_basket(
    root: Path,
    *,
    top_n: int = 5,
    market: str = "KOSPI",
) -> list[BasketName]:
    """현재 Soft Lab top_n (QV Soft 주간과 동일 파라미터).

    주의: mid Lab 가격·점수는 루트 alpha_portfolio(코스피 중심) 경로.
    코스닥 장부 전용 Soft 바스켓은 아직 분리되지 않음 → KOSDAQ이면 [].
    """
    from alpha_system.shadow.profit_lab import (
        build_sufficient_mid_weeks,
        load_mid_params_from_best,
    )

    root = Path(root)
    mkt = str(market or "KOSPI").upper()
    if mkt != "KOSPI":
        # 루트 Lab은 코스피 중심 · 코스닥/ALL 혼입 금지
        return []
    cfg = load_mid_params_from_best(root)
    n = int(getattr(cfg, "top_n", None) or top_n)
    weeks, meta = build_sufficient_mid_weeks(
        root, lookback_trading_days=60, ensure_prices=False, params=cfg
    )
    names = _name_map(root)
    tickers: list[str] = []
    if weeks:
        last = weeks[-1]
        tickers = [norm_ticker(t) for t in (last.tickers or []) if norm_ticker(t)]
    if not tickers:
        from alpha_system.shadow.profit_lab import load_qv_ranked_tickers

        tickers = load_qv_ranked_tickers(root, top_pool=max(20, n))[:n]
    tickers = [t for t in tickers if t][:n]
    if not tickers:
        return []
    w = 100.0 / len(tickers)
    soft_budget = 50.0
    of_each = soft_budget / len(tickers)
    note = f"mid_lab · {meta.get('params_label') or cfg.label} · as_of={meta.get('as_of_last')}"
    return [
        BasketName(
            ticker=tk,
            name=names.get(tk, tk),
            sleeve="soft",
            weight_in_sleeve=round(w, 2),
            of_mid_soft_pct=round(of_each, 2),
            note=note,
        )
        for tk in tickers
    ]


def load_activist_basket(
    root: Path,
    *,
    market: str = "KOSPI",
    soft_tickers: Sequence[str] | None = None,
) -> list[BasketName]:
    from alpha_system.review.treasury_activist_proposal import build_activist_proposal

    board = build_activist_proposal(
        Path(root), market=market, soft_tickers=soft_tickers
    )
    out: list[BasketName] = []
    for r in board.rows:
        out.append(
            BasketName(
                ticker=r.ticker,
                name=r.name,
                sleeve="activist",
                weight_in_sleeve=float(r.of_theme_sleeve_pct),
                of_mid_soft_pct=float(r.of_mid_soft_pct),
                note=f"stage={r.stage_id} · seat={r.seat_pct:g}%",
            )
        )
    return out


def _sleeve_ret(names: Sequence[BasketName], base_ret: float) -> float:
    if not names:
        return 0.0  # 공백 → 단기채≈0 가정
    # equal sleeve weight already in names; path ret = base (name tilt optional later)
    return float(base_ret)


def _blend(
    soft_ret: float,
    act_ret: float,
    *,
    soft_pct: float = 50.0,
    act_pct: float = 50.0,
    soft_empty: bool,
    act_empty: bool,
) -> float:
    """중기 Soft 예산 100 기준 50/50. 빈 축은 현금 0."""
    s = 0.0 if soft_empty else soft_ret
    a = 0.0 if act_empty else act_ret
    return (soft_pct / 100.0) * s + (act_pct / 100.0) * a


def _deployed_blend(
    soft_ret: float,
    act_ret: float,
    soft_names: Sequence[BasketName],
    act_names: Sequence[BasketName],
) -> tuple[float, float, float]:
    """실제 of_mid_soft% 가중 · 잔여는 현금 0."""
    soft_w = sum(float(n.of_mid_soft_pct) for n in soft_names) / 100.0
    act_w = sum(float(n.of_mid_soft_pct) for n in act_names) / 100.0
    cash_w = max(0.0, 1.0 - soft_w - act_w)
    ret = soft_w * soft_ret + act_w * act_ret + cash_w * 0.0
    return round(ret, 4), round(soft_w, 4), round(act_w, 4)


def build_scenario_board(
    root: Path | None = None,
    *,
    market: str = "KOSPI",
) -> ScenarioBoard:
    root = Path(root or ".")
    mkt = str(market or "KOSPI").upper()
    soft = load_soft_basket(root, market=mkt)
    soft_tks = [n.ticker for n in soft]
    act = load_activist_basket(root, market=mkt, soft_tickers=soft_tks)
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    scenarios: dict[str, dict[str, Any]] = {}
    for key, sc in SCENARIOS.items():
        soft_r = _sleeve_ret(soft, float(sc["soft_ret"]))
        act_r = _sleeve_ret(act, float(sc["activist_ret"]))
        blend = _blend(
            soft_r,
            act_r,
            soft_empty=not soft,
            act_empty=not act,
        )
        dep_ret, soft_w, act_w = _deployed_blend(soft_r, act_r, soft, act)
        scenarios[key] = {
            "label_ko": sc["label_ko"],
            "horizon_years": sc["horizon_years"],
            "koizumi_map": sc["koizumi_map"],
            "kospi_ret": sc["kospi_ret"],
            "soft_ret": round(soft_r, 4),
            "activist_ret": round(act_r, 4),
            "blend_50_50_ret": round(blend, 4),
            "deployed_ret": dep_ret,
            "deployed_soft_w": soft_w,
            "deployed_activist_w": act_w,
            "mdd_soft": sc["mdd_soft"],
            "mdd_activist": sc["mdd_activist"],
            "mdd_blend": sc["mdd_blend"],
            "soft_n": len(soft),
            "activist_n": len(act),
            "soft_empty_cash": not soft,
            "activist_empty_cash": not act,
            "vs_kospi_soft": round(soft_r - float(sc["kospi_ret"]), 4),
            "vs_kospi_activist": round(act_r - float(sc["kospi_ret"]), 4),
            "vs_kospi_blend": round(blend - float(sc["kospi_ret"]), 4),
        }
    return ScenarioBoard(
        as_of=as_of,
        market=mkt,
        soft_names=soft,
        activist_names=act,
        scenarios=scenarios,
    )


def persist_board(board: ScenarioBoard, root: Path | None = None) -> Path:
    root = Path(root or ".")
    path = root / OUT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(board.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def scenario_table_rows(board: ScenarioBoard) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, sc in board.scenarios.items():
        rows.append(
            {
                "시나리오": key,
                "라벨": sc["label_ko"],
                "년": sc["horizon_years"],
                "코스피": sc["kospi_ret"],
                "Soft": sc["soft_ret"],
                "행동주의": sc["activist_ret"],
                "50/50만기": sc["blend_50_50_ret"],
                "실배치": sc["deployed_ret"],
                "MDD블렌드": sc["mdd_blend"],
            }
        )
    return rows


__all__ = [
    "KOIZUMI_BENCH_NOTE",
    "OUT_REL",
    "SCENARIOS",
    "BasketName",
    "ScenarioBoard",
    "build_scenario_board",
    "persist_board",
    "scenario_table_rows",
]
