"""정적 배분 북 — 여러 레시피를 하나로 묶어 운영 (Review-only)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alpha_system.shadow.household_alloc_lab import load_recipes, load_report

# 사이드바에는 static_book 하나만 · 내부 레시피 id
STATIC_RECIPE_IDS: tuple[str, ...] = (
    "sixty_forty",
    "all_seasons",
    "permanent",
    "permanent_multi",
    "golden_butterfly",
    "k_all_weather",
    "compass_fit",
)

# 운영 본체 = 나침반 적합 정의 (평균회귀·다지역·_REF) · Lab 성적 1등과 분리
OPS_BODY_RECIPE = "compass_fit"
DEFAULT_STATIC_RECIPE = OPS_BODY_RECIPE


def static_recipe_meta(root: Path) -> list[dict[str, Any]]:
    """레시피 목록 + Lab CAGR/MDD (있으면)."""
    try:
        raw = load_recipes(root)
    except Exception:  # noqa: BLE001
        raw = {}
    report = load_report(root) or {}
    by_lab = {
        str(s.get("id")): s
        for s in (report.get("strategies") or [])
        if isinstance(s, dict) and s.get("id")
    }
    out: list[dict[str, Any]] = []
    for stg in raw.get("strategies") or []:
        if not isinstance(stg, dict):
            continue
        sid = str(stg.get("id") or "")
        if sid not in STATIC_RECIPE_IDS:
            continue
        lab = by_lab.get(sid) or {}
        cagr = lab.get("cagr") if lab.get("ok") else None
        mdd = lab.get("max_drawdown") if lab.get("ok") else None
        out.append(
            {
                "id": sid,
                "name_ko": str(stg.get("name_ko") or sid),
                "source": str(stg.get("source") or ""),
                "rebalance": str(stg.get("rebalance") or "annual_jan"),
                "cagr": cagr,
                "max_drawdown": mdd,
                "lab_ok": bool(lab.get("ok")),
            }
        )
    return out


def recommend_static_recipe(root: Path) -> str:
    """운영 본체 id · Lab CAGR 1등이 아님 · Executable select 제외."""
    try:
        from alpha_system.economy_compass.static_body_pick import (
            build_static_body_pick,
        )

        board = build_static_body_pick(Path(root), ensure_fetch=False)
        if board.ok and board.pick_id in STATIC_RECIPE_IDS:
            return board.pick_id
    except Exception:  # noqa: BLE001
        pass
    ids = {m["id"] for m in static_recipe_meta(root)}
    if OPS_BODY_RECIPE in ids:
        return OPS_BODY_RECIPE
    if DEFAULT_STATIC_RECIPE in ids:
        return DEFAULT_STATIC_RECIPE
    return DEFAULT_STATIC_RECIPE if not ids else next(iter(ids))


def recipe_select_labels(root: Path) -> list[tuple[str, str]]:
    """(id, selectbox label)."""
    rows = []
    for m in static_recipe_meta(root):
        if m.get("lab_ok") and m.get("cagr") is not None:
            tag = f"CAGR {100.0 * float(m['cagr']):+.1f}%"
        else:
            tag = "Lab—"
        rows.append((str(m["id"]), f"{m['name_ko']} · {tag}"))
    return rows


def checklist_static(recipe_id: str) -> list[str]:
    return [
        f"활성 레시피: {recipe_id}",
        "목표 비중표를 증권·연금 잔고와 대조",
        "매년 1월(또는 지정일)에만 리밸 · 평소 홀드",
        "레버리지·인버스 금지 · Soft·듀얼과 합산 집행 금지",
        "일상 데이터=확인① · ETF 가격 Lab은 필요 시 이 탭 갱신",
    ]


__all__ = [
    "DEFAULT_STATIC_RECIPE",
    "OPS_BODY_RECIPE",
    "STATIC_RECIPE_IDS",
    "checklist_static",
    "recipe_select_labels",
    "recommend_static_recipe",
    "static_recipe_meta",
]
