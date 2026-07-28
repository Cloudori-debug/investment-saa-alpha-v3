"""Run price + fundamentals refresh on the host PC."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
import time
from typing import Any


@dataclass
class RefreshResult:
    ok: bool
    message: str
    detail: dict[str, Any]


def _is_krx_timeout(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "timed out" in text or "timeout" in text or "data.krx.co.kr" in text


def _format_refresh_error(exc: BaseException) -> str:
    if _is_krx_timeout(exc):
        return (
            "KRX(data.krx.co.kr) 응답 지연·타임아웃입니다. "
            "일시적 장애인 경우가 많으니 1~2분 뒤 다시 시도하세요. "
            "설정 → KRX 테스트로 연결을 확인할 수 있습니다."
        )
    return str(exc)


def run_data_refresh(data_dir: Path, *, scope: str = "holdings") -> RefreshResult:
    """
    Invoke existing PyKRX bulk collect (prices + fundamentals).
    Runs locally on the machine hosting Streamlit — not a remote API.
    """
    try:
        from src.settings.user_secrets import apply_secrets_to_env
        from src.data_refresh.pykrx_bulk import run_pykrx_bulk_collect
    except ImportError as exc:
        return RefreshResult(
            ok=False,
            message="수집 모듈을 불러올 수 없습니다.",
            detail={"error": str(exc)},
        )

    apply_secrets_to_env(data_dir)
    positions_path = data_dir / "positions.csv"
    if scope == "holdings" and not positions_path.exists():
        return RefreshResult(
            ok=False,
            message=(
                "positions.csv가 없습니다. data/positions.csv를 복구하거나 "
                "보유 목록을 넣은 뒤 다시 시도하세요."
            ),
            detail={"error": "missing_positions_csv", "path": str(positions_path)},
        )

    last_exc: BaseException | None = None
    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            result = run_pykrx_bulk_collect(
                data_dir,
                scope=scope,
                merge_existing_universe=True,
                write_history=True,
                enrich_dart=True,
            )
            return RefreshResult(
                ok=True,
                message="현재가·펀더멘털 갱신 완료",
                detail={
                    "as_of": getattr(result, "as_of", None),
                    "tickers": getattr(result, "tickers_processed", None),
                    "errors": getattr(result, "errors", None),
                    "attempts": attempt,
                },
            )
        except Exception as exc:
            last_exc = exc
            if attempt < attempts and _is_krx_timeout(exc):
                time.sleep(3 * attempt)
                continue
            break

    assert last_exc is not None
    return RefreshResult(
        ok=False,
        message=_format_refresh_error(last_exc),
        detail={"error": str(last_exc), "attempts": attempts},
    )


def run_quant_snapshot_refresh(
    root: Path,
    *,
    collect_scope: str = "liquid",
) -> RefreshResult:
    """One-click collection: operational data, then alpha quant snapshot.

    The subprocess isolates alpha_portfolio's local ``src`` package from the
    dashboard's top-level ``src`` package. No target portfolio writer is called.
    Blocked while weekly proposal freeze is active.
    """
    from alpha_system.ui.services.proposal_freeze import (
        assert_quant_refresh_allowed,
        block_message,
        is_freeze_active,
    )

    if is_freeze_active(root):
        try:
            assert_quant_refresh_allowed(root)
        except RuntimeError as exc:
            return RefreshResult(
                ok=False,
                message=str(exc) or block_message(root=root),
                detail={"blocked_by": "weekly_qual_proposal_freeze"},
            )

    operational = run_data_refresh(root / "data", scope="holdings")
    if not operational.ok:
        return RefreshResult(
            ok=False,
            message=f"운용 데이터 갱신 실패: {operational.message}",
            detail={"operational": operational.detail},
        )

    script = root / "scripts" / "run_alpha_quant_snapshot.py"
    command = [
        sys.executable,
        str(script),
        "--root",
        str(root),
        "--collect",
        "--collect-scope",
        collect_scope,
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1200,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return RefreshResult(
            ok=False,
            message=f"정량 스냅샷 실행 실패: {exc}",
            detail={"operational": operational.detail, "error": str(exc)},
        )

    detail: dict[str, Any] = {
        "operational": operational.detail,
        "command": "run_alpha_quant_snapshot.py --collect --collect-scope "
        + collect_scope,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "target_portfolio_written": False,
    }
    if completed.returncode != 0:
        return RefreshResult(
            ok=False,
            message="정량 스냅샷 생성 실패",
            detail=detail,
        )

    provenance = root / "data" / "alpha_quant_snapshot_provenance.json"
    if provenance.exists():
        try:
            import json

            detail["provenance"] = json.loads(provenance.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            detail["provenance_path"] = str(provenance)
    return RefreshResult(
        ok=True,
        message="정량 데이터·alpha_scores 갱신 완료",
        detail=detail,
    )


def _tail_lines(text: str, n: int = 40) -> str:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) <= n:
        return "\n".join(lines)
    return "\n".join(lines[-n:])


def _regime_snapshot(root: Path) -> dict[str, Any]:
    """Best-effort read of Tier-1 / regime sync state after analysis."""
    out: dict[str, Any] = {}
    mi_path = root / "data" / "market_indicators.csv"
    if mi_path.exists():
        try:
            import pandas as pd

            df = pd.read_csv(mi_path, dtype=str, keep_default_na=False)
            if not df.empty:
                row = df.iloc[-1]
                out["market_as_of"] = str(row.get("date") or "")
                out["regime"] = str(row.get("regime") or "")
                out["regime_expires"] = str(row.get("regime_expires_date") or "")
        except Exception as exc:
            out["market_read_error"] = str(exc)
    suggestion = root / "outputs" / "regime_auto_suggestion.json"
    if suggestion.exists():
        try:
            import json

            doc = json.loads(suggestion.read_text(encoding="utf-8"))
            out["regime_synced"] = bool(doc.get("auto_synced"))
            out["computed_regime"] = doc.get("computed_regime")
            out["applied_regime"] = doc.get("applied_regime")
        except Exception as exc:
            out["regime_suggestion_error"] = str(exc)
    health_path = root / "outputs" / "system_health.json"
    if health_path.exists():
        try:
            import json

            health = json.loads(health_path.read_text(encoding="utf-8"))
            out["health_overall"] = health.get("overall")
            for check in health.get("checks") or []:
                if check.get("name") == "core_price_gate":
                    out["core_price_gate"] = check.get("status")
                    out["core_price_gate_message"] = check.get("message")
                    break
        except Exception as exc:
            out["health_read_error"] = str(exc)
    return out


def run_compass_analysis(
    root: Path,
    *,
    run_mode: str = "standard",
    no_backtest: bool = False,
    timeout_sec: int = 1800,
) -> RefreshResult:
    """Run launcher [3] Analysis (`python -m src.main`) without approving target writes.

    Always passes ``--refresh-market`` so Tier-1 ``market_indicators``, Tier-A
    prices, and regime auto-sync run before analysis (standard mode alone is
    cache-first and would leave as_of / core prices stale). Does **not** pass
    ``--approve-target`` so ``target_portfolio.csv`` stays human-only.
    """
    mode = (run_mode or "standard").strip().lower() or "standard"
    command = [
        sys.executable,
        "-m",
        "src.main",
        "--data-dir",
        str(root / "data"),
        "--output-dir",
        str(root / "outputs"),
        "--run-mode",
        mode,
        "--refresh-market",
    ]
    if no_backtest:
        command.append("--no-backtest")

    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return RefreshResult(
            ok=False,
            message=(
                f"나침반 분석이 {timeout_sec // 60}분 안에 끝나지 않았습니다. "
                "장중·KRX 지연 시 런처 [3]로 다시 시도하세요."
            ),
            detail={"error": str(exc), "command": command},
        )
    except OSError as exc:
        return RefreshResult(
            ok=False,
            message=f"나침반 분석 실행 실패: {exc}",
            detail={"error": str(exc)},
        )

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    detail: dict[str, Any] = {
        "command": " ".join(command),
        "returncode": completed.returncode,
        "stdout_tail": _tail_lines(stdout),
        "stderr_tail": _tail_lines(stderr),
        "target_portfolio_written": False,
        "approve_target": False,
    }
    for line in stdout.splitlines():
        low = line.lower()
        if "actual buy allowed" in low:
            detail["actual_buy_allowed"] = line.split(":", 1)[-1].strip()
        if "data gate" in low:
            detail["data_gate"] = line.split(":", 1)[-1].strip()
        if low.startswith("health:"):
            detail["health"] = line.split(":", 1)[-1].strip()
        if low.startswith("run mode:"):
            detail["run_mode_line"] = line.strip()

    snap = _regime_snapshot(root)
    detail.update(snap)

    gate = str(detail.get("data_gate") or "").upper()
    regime_ok = bool(snap.get("market_as_of")) and (
        snap.get("regime_synced") is True
        or str(snap.get("regime") or "").upper() not in {"", "NEUTRAL", "AUTO"}
    )

    if completed.returncode != 0:
        # Regime Tier-1 may have refreshed even when full pipeline exits 1 on RED.
        if regime_ok and gate == "RED":
            price_msg = snap.get("core_price_gate_message") or "core ETF 시세 stale"
            bits = [
                f"레짐·Tier-1 갱신됨 (as_of {snap.get('market_as_of')}",
                f"레짐 {snap.get('applied_regime') or snap.get('regime')})",
                f"Data Gate RED — 실행 차단 ({price_msg})",
                "홈「정량 전체 갱신」또는 설정「시장지표 갱신」후 재실행",
            ]
            return RefreshResult(ok=True, message=" · ".join(bits), detail=detail)
        hint = (
            snap.get("core_price_gate_message")
            or detail.get("data_gate")
            or detail.get("stderr_tail")
            or detail.get("stdout_tail")
        )
        return RefreshResult(
            ok=False,
            message=f"나침반 분석 실패 (exit {completed.returncode})"
            + (f" · {hint}" if hint else ""),
            detail=detail,
        )

    bits = ["나침반·레짐 분석 완료"]
    if snap.get("market_as_of"):
        bits.append(f"as_of {snap['market_as_of']}")
    if detail.get("data_gate"):
        bits.append(f"Data Gate {detail['data_gate']}")
    if detail.get("actual_buy_allowed") is not None:
        bits.append(f"Actual Buy {detail['actual_buy_allowed']}")
    return RefreshResult(ok=True, message=" · ".join(bits), detail=detail)
