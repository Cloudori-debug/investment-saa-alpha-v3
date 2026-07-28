from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.data_provenance import audit_market_data_consistency
from src.trim_sizing import trim_config_from_rules


def regime_expiry_check(
    ref_date: str | None,
    expires_date: str | None,
    *,
    regime: str | None = None,
) -> tuple[str, str]:
    """수동 레짐 만료 — PASS: D-3+, WARN: D-0~1, FAIL: 만료됨."""
    from datetime import datetime

    if not expires_date:
        return "todo", "만료일 미설정 — market_indicators.csv 확인"
    if not ref_date:
        return "todo", f"만료 {expires_date}"
    try:
        ref_d = datetime.strptime(str(ref_date)[:10], "%Y-%m-%d").date()
        exp_d = datetime.strptime(str(expires_date)[:10], "%Y-%m-%d").date()
    except ValueError:
        return "warn", f"만료 {expires_date} (날짜 형식 오류)"

    days_left = (exp_d - ref_d).days
    reg = f" · 레짐 {regime}" if regime else ""
    detail = f"만료 {expires_date} (기준 {ref_date}, D-{days_left}){reg}"
    if days_left < 0:
        return "fail", detail
    if days_left <= 1:
        return "warn", detail
    if days_left >= 3:
        return "pass", detail
    return "warn", detail


@dataclass(frozen=True)
class ChecklistItem:
    id: str
    label: str
    status: str  # pass | warn | fail | todo
    detail: str = ""


def _load_acceptance(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "acceptance_report.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_decision_log_last(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "decision_log.jsonl"
    if not path.exists():
        return {}
    last_line = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            last_line = stripped
    if not last_line:
        return {}
    try:
        return json.loads(last_line)
    except json.JSONDecodeError:
        return {}


def _load_authoritative_state(output_dir: Path) -> dict[str, Any]:
    """daily_report·체크리스트용 — final > acceptance > decision_log 마지막 줄."""
    final_path = output_dir / "final_execution_decision.json"
    if final_path.exists():
        final = json.loads(final_path.read_text(encoding="utf-8"))
        return {
            "overall": final.get("system_status") or final.get("overall", "YELLOW"),
            "execution_scope": final.get("execution_scope", "—"),
            "alpha_approval": final.get("alpha_approval", "—"),
            "alpha_position_action": final.get("alpha_position_action", "—"),
            "dry_run_days": int(final.get("dry_run_days", 0)),
            "data_gate": final.get("data_gate"),
            "data_gate_detail": final.get("data_gate_detail") or {},
            "operational_verdict": final.get("operational_verdict", ""),
            "source": "final_execution_decision",
        }

    ac = _load_acceptance(output_dir)
    if ac:
        return {
            "overall": ac.get("overall", "YELLOW"),
            "execution_scope": ac.get("execution_scope", "—"),
            "alpha_approval": ac.get("alpha_approval", "—"),
            "dry_run_days": int(ac.get("dry_run_days", 0)),
            "data_gate": None,
            "data_gate_detail": {},
            "operational_verdict": ac.get("operational_verdict", ""),
            "source": "acceptance_report",
        }

    log = _load_decision_log_last(output_dir)
    if log:
        return {
            "overall": log.get("data_gate", "YELLOW"),
            "execution_scope": log.get("execution_scope", "—"),
            "alpha_approval": log.get("alpha_approval", "—"),
            "dry_run_days": 0,
            "data_gate": log.get("data_gate"),
            "data_gate_detail": log.get("data_gate_detail") or {},
            "operational_verdict": "",
            "source": "decision_log",
        }
    return {
        "overall": "YELLOW",
        "execution_scope": "—",
        "alpha_approval": "—",
        "dry_run_days": 0,
        "data_gate": None,
        "data_gate_detail": {},
        "operational_verdict": "",
        "source": "default",
    }


def _load_trade_actions(output_dir: Path) -> pd.DataFrame | None:
    path = output_dir / "trade_actions.csv"
    if not path.exists():
        return None
    return pd.read_csv(path, dtype=str)


def _stale_days(data_dir: Path, as_of: str | None) -> int | None:
    path = data_dir / "market_data_provenance.json"
    if not path.exists():
        return None
    fields = (json.loads(path.read_text(encoding="utf-8")).get("fields") or {})
    if not fields:
        return None
    return max(int(v.get("stale_business_days", 0)) for v in fields.values())


def build_real_investment_checklist(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str | None = None,
) -> list[ChecklistItem]:
    """실투자 1주일 단계 — 매일 확인용 체크리스트."""
    state = _load_authoritative_state(output_dir)
    scope = state["execution_scope"]
    alpha = state["alpha_approval"]
    alpha_pos = state.get("alpha_position_action", "—")
    dry = state["dry_run_days"]
    overall = state["overall"]
    gate_detail = state["data_gate_detail"]
    data_gate = state.get("data_gate")
    market_as_of = as_of
    if not market_as_of:
        mi = data_dir / "market_indicators.csv"
        if mi.exists():
            df = pd.read_csv(mi, dtype=str, nrows=1)
            if not df.empty and "date" in df.columns:
                market_as_of = str(df.iloc[0]["date"])

    stale = _stale_days(data_dir, market_as_of)
    market_audit = audit_market_data_consistency(data_dir)
    reanalysis = bool(market_audit.get("reanalysis_required"))
    regime_expiry_detail = "—"
    regime_expiry_status = "todo"
    mi = data_dir / "market_indicators.csv"
    if mi.exists():
        from src.data_loader import load_market_indicators

        mkt = load_market_indicators(mi)
        ref = as_of or market_as_of or mkt.date
        regime_expiry_status, regime_expiry_detail = regime_expiry_check(
            ref,
            getattr(mkt, "regime_expires_date", None),
            regime=getattr(mkt, "regime", None),
        )
    trade = _load_trade_actions(output_dir)

    buy_candidates: list[str] = []
    trim_candidates: list[str] = []
    step_frac, max_step = 1 / 3, 2.0
    tr_path = data_dir / "trigger_rules.yaml"
    if tr_path.exists():
        from src.config import load_yaml

        step_frac, max_step = trim_config_from_rules(load_yaml(tr_path))
    if trade is not None and not trade.empty:
        for _, row in trade.iterrows():
            action = str(row.get("action", ""))
            name = str(row.get("name", row.get("ticker", "")))
            ticker = str(row.get("ticker", ""))
            if ticker == "PORTFOLIO":
                continue
            if action in {"Buy", "BuyCandidate", "Buy-allowed"}:
                buy_candidates.append(f"{name} ({ticker})")
            elif action == "Trim":
                try:
                    step = abs(float(row.get("allowed_size_pct", 0)))
                except (TypeError, ValueError):
                    step = 0.0
                hint = f"1회 {step:.1f}%p" if step > 0 else "부분만"
                trim_candidates.append(f"{name} ({ticker}) {hint}")
            elif action == "Park":
                pass  # funding source — Trim 후보 아님

    items: list[ChecklistItem] = [
        ChecklistItem(
            "R0",
            "데이터 기준일이 오늘(또는 최근 영업일)인가?",
            "pass" if stale is not None and stale <= 1 else "warn" if stale is not None else "todo",
            f"기준일 {market_as_of or '—'} · stale {stale if stale is not None else '?'}영업일",
        ),
        ChecklistItem(
            "R0b",
            "시장 데이터 정합·재분석 필요 여부",
            "fail" if reanalysis and stale is not None and stale > 5 else "warn" if reanalysis else "pass",
            (
                "; ".join(market_audit.get("issues") or [])
                or f"max stale {market_audit.get('max_stale_business_days', '—')}영업일"
            ),
        ),
        ChecklistItem(
            "R1",
            "전체 분석을 오늘 실행했는가?",
            "pass" if (output_dir / "run_manifest.json").exists() else "todo",
            "사이드바 ▶ 전체 분석 또는 scripts/daily_pipeline.py",
        ),
        ChecklistItem(
            "R1b",
            "수동 레짐 만료일 (manual regime expiry)",
            regime_expiry_status,
            regime_expiry_detail,
        ),
        ChecklistItem(
            "R2",
            "Execution Scope — ETF_ONLY: kr_alpha 신규·Replace 금지, risk-reduce Trim만 예외",
            "fail" if scope == "NO_TRADE" else "pass" if scope in {"ETF_ONLY", "ETF_ONLY_ALPHA_REVIEW"} else "warn",
            (
                f"현재: {scope} · alpha_position={alpha_pos}"
                + (
                    " — kr_alpha 상한 초과 시 Trim만 사람 승인·1회"
                    if alpha_pos == "RISK_REDUCE_ONLY"
                    else ""
                )
            ),
        ),
        ChecklistItem(
            "R3",
            "kr_alpha 신규매수 차단 준수",
            "pass"
            if scope in {"ETF_ONLY", "ETF_ONLY_ALPHA_REVIEW", "NO_TRADE"}
            or alpha in {"RESTRICTED", "BLOCKED"}
            else "warn",
            f"alpha_approval={alpha}",
        ),
        ChecklistItem(
            "R4",
            f"dry-run 누적 ({dry}/10 영업일)",
            "pass" if dry >= 10 else "warn",
            "10일 전까지는 소액·ETF만, 전액 리밸런싱 금지",
        ),
        ChecklistItem(
            "R5",
            "Executable Buy 후보 — 트리거 충족 후 본인 승인",
            "todo" if buy_candidates else "pass",
            ", ".join(buy_candidates) if buy_candidates else "Buy 후보 없음 (Wait 유지)",
        ),
        ChecklistItem(
            "R6",
            f"Trim 제안 — gap×{step_frac:.0%}·1회 최대 {max_step:.0f}%p (Park·Review-only 제외)",
            "warn" if trim_candidates else "pass",
            ", ".join(trim_candidates) if trim_candidates else "Trim 제안 없음",
        ),
        ChecklistItem(
            "R7",
            "운용 판정 GREEN/YELLOW — RED면 매매 보류",
            "pass" if overall in {"GREEN", "YELLOW"} else "fail",
            f"overall={overall}",
        ),
    ]
    if gate_detail.get("summary"):
        dg = data_gate or gate_detail.get("executable_gate") or overall
        r8_status = "fail" if dg == "RED" else "warn" if dg == "YELLOW" else "pass"
        items.append(
            ChecklistItem(
                "R8",
                "통합 data_gate 산출 근거",
                r8_status,
                str(gate_detail.get("summary", "")),
            )
        )
    return items


def build_executable_brief(
    data_dir: Path,
    output_dir: Path,
) -> str:
    """당일 Executable 액션만 요약 — final_execution_decision.json이 최종 권위."""
    from src.operating_state import OperatingStateBundle, format_operating_card_markdown

    ac = _load_acceptance(output_dir)
    trade = _load_trade_actions(output_dir)
    items = build_real_investment_checklist(data_dir, output_dir)
    final_path = output_dir / "final_execution_decision.json"
    final = {}
    if final_path.exists():
        final = json.loads(final_path.read_text(encoding="utf-8"))

    lines: list[str] = ["# 실투자 Executable 요약", ""]

    if final.get("operating_state"):
        bundle = OperatingStateBundle(
            operating_state=final["operating_state"],
            primary_user_action=final.get("primary_user_action", ""),
            allowed_scope_label=final.get("allowed_scope_label", ""),
            forbidden_actions=list(final.get("forbidden_actions") or []),
            has_executable_trade=bool(final.get("has_executable_trade")),
            has_executable_etf_trade=bool(final.get("has_executable_etf_trade")),
            has_executable_alpha_trade=bool(final.get("has_executable_alpha_trade")),
            has_theoretical_signal=bool(final.get("has_theoretical_signal")),
            blocked_reasons=list(final.get("blocked_reasons") or []),
            caution_reasons=list(final.get("caution_reasons") or []),
            secondary_tasks=list(final.get("secondary_tasks") or []),
            next_required_step=final.get("next_required_step", ""),
            executable_candidates=list(final.get("executable_candidates") or []),
        )
        lines.extend(format_operating_card_markdown(bundle, final=final))
        lines.append("---")
        lines.append("")

    lines.extend([
        "> **AUTHORITATIVE** — `final_execution_decision.json` · 아래는 상세 요약",
        "",
        f"- 운용 판정: **{final.get('system_status') or ac.get('overall', '—')}** · "
        f"Scope: `{final.get('execution_scope') or ac.get('execution_scope', '—')}`",
        f"- Alpha: `{final.get('alpha_approval') or ac.get('alpha_approval', '—')}` · "
        f"Alpha 실행: `{final.get('alpha_execution_status', '—')}` · "
        f"dry-run: **{final.get('dry_run_days', ac.get('dry_run_days', 0))}/10**",
        f"- Group gap 기준: `{final.get('group_gap_source', '—')}`",
        "",
    ])
    gate_detail = final.get("data_gate_detail") or {}
    if gate_detail.get("summary"):
        lines.extend([
            f"- **data_gate**: `{final.get('data_gate', '—')}` — {gate_detail.get('summary')}",
            "",
        ])
    market_audit = final.get("market_data_audit") or {}
    if market_audit.get("reanalysis_required"):
        issues = market_audit.get("issues") or []
        lines.extend([
            f"- **재분석 권고**: {'; '.join(issues) if issues else 'stale·기준일 불일치'}",
            "",
        ])

    lines.extend([
        final.get("operational_verdict") or ac.get("operational_verdict", ""),
        "",
        "## 오늘 할 수 있는 것",
        "",
        "- 포트 vs 목표 비중 점검 (`current_vs_target.csv`)",
        "- ETF·현금·채권: **Executable** 액션만 (트리거 + 본인 승인)",
        "- kr_alpha: **검토만** — 매수·교체 실행 금지",
        "",
        "## Executable 종목 액션",
        "",
    ])

    if trade is None or trade.empty:
        lines.append("_trade_actions.csv 없음 — 전체 분석 실행 필요_")
    else:
        exec_rows = trade[
            ~trade["ticker"].eq("PORTFOLIO")
            & ~trade["action"].eq("Review-only")
        ]
        review_rows = trade[trade["action"].eq("Review-only")]
        if exec_rows.empty:
            lines.append("_ETF·현금 Executable 액션 없음 (Wait/Hold 위주)_")
        else:
            lines.append("| Ticker | Name | Action | 1회 권장 | Reason |")
            lines.append("|--------|------|--------|--------:|--------|")
            for _, row in exec_rows.iterrows():
                action = str(row.get("action", ""))
                try:
                    step = abs(float(row.get("allowed_size_pct", 0)))
                except (TypeError, ValueError):
                    step = 0.0
                step_col = f"{step:.1f}%p" if action == "Trim" and step > 0 else "—"
                lines.append(
                    f"| {row.get('ticker', '')} | {row.get('name', '')} | "
                    f"{action} | {step_col} | {row.get('reason', '')} |"
                )
        if not review_rows.empty:
            lines.extend(["", "### kr_alpha — Review-only (실행 금지)", ""])
            for _, row in review_rows.head(8).iterrows():
                lines.append(f"- {row.get('name', '')} ({row.get('ticker', '')}): {row.get('reason', '')}")
            if len(review_rows) > 8:
                lines.append(f"- _외 {len(review_rows) - 8}종 — kr_alpha_review_actions.csv 참고_")

    lines.extend(["", "## 실투자 체크리스트", ""])
    icon = {"pass": "✅", "warn": "⚠️", "fail": "❌", "todo": "⬜"}
    for it in items:
        lines.append(f"- {icon.get(it.status, '·')} **{it.label}** — {it.detail}")

    lines.extend([
        "",
        "## 참고자료 (충돌 시 final_execution_decision.json 우선)",
        "",
        "- `trade_actions.csv` — Executable 종목 액션",
        "- `portfolio_actions.md` — 자산군 액션",
        "- `holdings_review.csv` / `alpha_candidates.csv` — 알파 연구용",
        "- `theoretical_trade_actions.csv` — 게이트 무시 이론값",
        "",
        "## 하면 안 되는 것",
        "",
        "- 알파 상위 종목 즉시 매수",
        "- theoretical Replace를 실제 매도로 해석",
        "- 리포트만 보고 전액 리밸런싱",
        "- 자동매매 연결",
        "",
        "> 소액 실투자: ETF 1종 · 계좌 5~15% · 한 번에 한 액션만.",
        "> Trim: gap의 1/3·1회 최대 2%p — 전량 매도 금지.",
    ])
    return "\n".join(lines)


def write_executable_brief(data_dir: Path, output_dir: Path) -> Path:
    path = output_dir / "executable_brief.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_executable_brief(data_dir, output_dir), encoding="utf-8")
    return path


def checklist_markdown_section(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str | None = None,
    section_no: int = 9,
) -> list[str]:
    items = build_real_investment_checklist(data_dir, output_dir, as_of=as_of)
    icon = {"pass": "✅", "warn": "⚠️", "fail": "❌", "todo": "⬜"}
    lines = [
        f"## {section_no}. 실투자 1주일 체크리스트",
        "",
        "> ETF·비중 점검 범위 소액 실투자. kr_alpha·전액 리밸런싱은 dry-run 10일 후 재평가.",
        "> Trim: gap의 1/3(최대 2%p/회)만 — 전량 Trim 금지.",
        "",
    ]
    for it in items:
        lines.append(f"- {icon.get(it.status, '·')} **{it.label}** — {it.detail}")
    lines.append("")
    return lines
