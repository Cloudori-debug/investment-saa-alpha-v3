from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCENARIOS = {
    "reform_success": {
        "label": "성공 (개혁·밸류업 실행)",
        "ops_hint": "저PBR·소각 테마 관찰 강화. scope 열리면 kr_alpha 단계 검토.",
    },
    "reform_delay": {
        "label": "지연 (말만 밸류업)",
        "ops_hint": "하케다카 리서치만. ETF·현금 유지. 개별주 신규 매수 보류.",
    },
    "stress_failure": {
        "label": "실패/스트레스 (PF·신용 경색)",
        "ops_hint": "방어 우선. 부동산형·W등급·복잡 지주 축소. 금융·유동성 경계.",
    },
}


@dataclass
class MacroScenarioResult:
    scenario_id: str
    label: str
    confidence: str
    score_success: int
    score_stress: int
    drivers: list[str]
    ops_hint: str
    kr_alpha_stance: str
    hakedaka_stance: str


def _load_market(data_dir: Path) -> dict[str, Any]:
    import pandas as pd

    path = data_dir / "market_indicators.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str, nrows=1)
    if df.empty:
        return {}
    return df.iloc[0].to_dict()


def _load_gate_context(output_dir: Path) -> dict[str, Any]:
    """거시·리서치 체크리스트용 — final > acceptance."""
    final_path = output_dir / "final_execution_decision.json"
    if final_path.exists():
        f = json.loads(final_path.read_text(encoding="utf-8"))
        return {
            "overall": str(f.get("system_status") or f.get("overall", "YELLOW")),
            "dry_run_days": int(f.get("dry_run_days", 0)),
            "execution_scope": str(f.get("execution_scope", "ETF_ONLY")),
            "alpha_approval": str(f.get("alpha_approval", "—")),
        }
    ac_path = output_dir / "acceptance_report.json"
    if ac_path.exists():
        ac = json.loads(ac_path.read_text(encoding="utf-8"))
        return {
            "overall": str(ac.get("overall", "YELLOW")),
            "dry_run_days": int(ac.get("dry_run_days", 0)),
            "execution_scope": str(ac.get("execution_scope", "ETF_ONLY")),
            "alpha_approval": str(ac.get("alpha_approval", "—")),
        }
    return {
        "overall": "YELLOW",
        "dry_run_days": 0,
        "execution_scope": "ETF_ONLY",
        "alpha_approval": "—",
    }


def evaluate_macro_scenario(data_dir: Path, output_dir: Path) -> MacroScenarioResult:
    market = _load_market(data_dir)
    ctx = _load_gate_context(output_dir)

    success = 0
    stress = 0
    drivers: list[str] = []

    try:
        kospi = float(market.get("kospi", 0))
        high = float(market.get("kospi_recent_high", kospi) or kospi)
        vix = float(market.get("vix", 0))
        if high > 0 and kospi > 0:
            dd = (high - kospi) / high
            if dd >= 0.12:
                stress += 3
                drivers.append(f"KOSPI 고점 대비 -{dd*100:.1f}%")
            elif dd >= 0.06:
                stress += 1
                drivers.append(f"KOSPI 조정 -{dd*100:.1f}%")
            else:
                success += 1
        if vix >= 28:
            stress += 2
            drivers.append(f"VIX {vix:.1f} (고변동)")
        elif vix >= 22:
            stress += 1
            drivers.append(f"VIX {vix:.1f}")
        else:
            success += 1
    except (TypeError, ValueError):
        drivers.append("시장지표 파싱 불가")

    overall = ctx["overall"]
    dry = ctx["dry_run_days"]
    scope = ctx["execution_scope"]

    if overall == "GREEN":
        success += 2
        drivers.append("운용승인 GREEN")
    elif overall == "YELLOW":
        success += 1
        stress += 1
        drivers.append("운용승인 YELLOW")
    else:
        stress += 3
        drivers.append("운용승인 RED")

    if dry >= 7:
        success += 2
        drivers.append(f"dry-run {dry}/10")
    elif dry >= 3:
        success += 1
        drivers.append(f"dry-run {dry}/10 진행")
    else:
        stress += 1
        drivers.append(f"dry-run {dry}/10 부족")

    if scope == "ETF_ONLY":
        stress += 1
        drivers.append("ETF_ONLY — kr_alpha 실행 제한")
    elif scope == "NO_TRADE":
        stress += 2
        drivers.append("NO_TRADE")

    health_path = output_dir / "system_health.json"
    if health_path.exists():
        health = json.loads(health_path.read_text(encoding="utf-8"))
        if int(health.get("summary", {}).get("fail", 0)) > 0:
            stress += 2
            drivers.append("system_health fail>0")

    if stress - success >= 2:
        sid = "stress_failure"
        conf = "high" if stress - success >= 4 else "medium"
    elif success - stress >= 2:
        sid = "reform_success"
        conf = "medium"
    else:
        sid = "reform_delay"
        conf = "medium"

    meta = SCENARIOS[sid]
    return MacroScenarioResult(
        scenario_id=sid,
        label=meta["label"],
        confidence=conf,
        score_success=success,
        score_stress=stress,
        drivers=drivers,
        ops_hint=meta["ops_hint"],
        kr_alpha_stance="review_only" if scope in {"ETF_ONLY", "NO_TRADE"} else "conditional",
        hakedaka_stance="track" if sid != "stress_failure" else "defensive_track",
    )


def write_macro_scenario(data_dir: Path, output_dir: Path) -> Path:
    result = evaluate_macro_scenario(data_dir, output_dir)
    payload = {
        "schema_version": "1.0",
        "scenario_id": result.scenario_id,
        "label": result.label,
        "confidence": result.confidence,
        "score_success": result.score_success,
        "score_stress": result.score_stress,
        "drivers": result.drivers,
        "ops_hint": result.ops_hint,
        "kr_alpha_stance": result.kr_alpha_stance,
        "hakedaka_stance": result.hakedaka_stance,
        "scenarios_reference": SCENARIOS,
    }
    path = output_dir / "macro_scenario.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    regime_path = output_dir / "compass_regime.json"
    if regime_path.exists():
        regime = json.loads(regime_path.read_text(encoding="utf-8"))
        regime["macro_scenario"] = {
            "id": result.scenario_id,
            "label": result.label,
            "ops_hint": result.ops_hint,
        }
        regime_path.write_text(json.dumps(regime, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
