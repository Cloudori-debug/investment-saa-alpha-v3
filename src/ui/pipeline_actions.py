from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.runtime.run_mode import RunMode


@dataclass
class FullAnalysisResult:
    market_as_of: str | None = None
    market_refreshed: bool = False
    market_warnings: list[str] = field(default_factory=list)
    run_mode: str = RunMode.STANDARD.value
    actual_buy_allowed: int = 0
    advisory_note: str = ""
    runtime_profile_path: str = "outputs/runtime_profile.json"
    runtime_profile: dict[str, Any] = field(default_factory=dict)


def run_full_analysis(
    data_dir: Path,
    output_dir: Path,
    *,
    auto_decompose: bool = True,
    run_backtest: bool = False,
    refresh_market: bool = True,
    run_mode: str | RunMode = RunMode.STANDARD,
    on_step: Callable[[str, str, float], None] | None = None,
    progress: Any | None = None,
) -> FullAnalysisResult:
    """사이드바·대시보드 공통 — run mode별 분석 실행."""
    from src.runtime.pipeline_runner import run_pipeline_with_mode
    from src.runtime.run_mode import resolve_run_config

    cfg = resolve_run_config(run_mode)
    result = FullAnalysisResult(run_mode=cfg.run_mode.value, advisory_note=cfg.advisory_note)
    step_cb = on_step
    if progress is not None and hasattr(progress, "profiler_callback"):
        step_cb = progress.profiler_callback

    refresh = refresh_market and cfg.run_mode in {RunMode.STANDARD, RunMode.DEEP}
    if refresh:
        if progress is not None and hasattr(progress, "on_pre_step"):
            progress.on_pre_step("market_refresh", phase="start")
        from src.data_refresh.market_indicators_refresh import refresh_all_market_indicators

        try:
            mi = refresh_all_market_indicators(data_dir)
            result.market_as_of = mi.as_of
            result.market_refreshed = True
            result.market_warnings = list(mi.warnings) + list(mi.errors)
        except Exception as exc:
            result.market_warnings.append(f"시장지표 갱신 실패: {exc}")
        finally:
            if progress is not None and hasattr(progress, "on_pre_step"):
                progress.on_pre_step("market_refresh", phase="end")

    if cfg.run_mode not in {RunMode.QUICK, RunMode.BUNDLE_ONLY}:
        as_of_prices = result.market_as_of
        if not as_of_prices:
            path = data_dir / "market_indicators.csv"
            if path.exists():
                import pandas as pd

                df = pd.read_csv(path, dtype=str, nrows=1)
                if not df.empty and "date" in df.columns:
                    as_of_prices = str(df.iloc[0]["date"])
        if as_of_prices and cfg.run_mode in {RunMode.STANDARD, RunMode.DEEP}:
            if progress is not None and hasattr(progress, "on_pre_step"):
                progress.on_pre_step("tier_a_prices", phase="start")
            from src.data_refresh.prices_refresh import ensure_tier_a_prices

            try:
                tier = ensure_tier_a_prices(
                    data_dir,
                    as_of_prices,
                    output_dir=output_dir,
                    top_n=50,
                    refresh_existing=True,
                )
                if tier.failed:
                    result.market_warnings.append(
                        f"Tier A 시세 갱신 실패 {len(tier.failed)}종: {', '.join(tier.failed[:5])}"
                    )
            except Exception as exc:
                result.market_warnings.append(f"Tier A 시세 갱신 실패: {exc}")
            finally:
                if progress is not None and hasattr(progress, "on_pre_step"):
                    progress.on_pre_step("tier_a_prices", phase="end")

    pipe = run_pipeline_with_mode(
        data_dir,
        output_dir,
        run_mode=run_mode,
        auto_decompose=auto_decompose,
        refresh_market=False,
        run_backtest=run_backtest,
        entrypoint="streamlit",
        on_step=step_cb,
    )
    result.actual_buy_allowed = pipe.actual_buy_allowed
    result.advisory_note = pipe.advisory_note

    from src.report.io_utils import read_output_json

    result.runtime_profile = read_output_json(output_dir / "runtime_profile.json") or {}

    if not result.market_as_of:
        path = data_dir / "market_indicators.csv"
        if path.exists():
            import pandas as pd

            df = pd.read_csv(path, dtype=str, nrows=1)
            if not df.empty and "date" in df.columns:
                result.market_as_of = str(df.iloc[0]["date"])

    return result


def run_post_target_approval_analysis(
    data_dir: Path,
    output_dir: Path,
    *,
    progress: Any | None = None,
) -> FullAnalysisResult:
    """승인 직후 권장 루틴 — STANDARD, 시장지표·Tier A 갱신 생략."""
    return run_full_analysis(
        data_dir,
        output_dir,
        auto_decompose=True,
        run_backtest=False,
        refresh_market=False,
        run_mode=RunMode.STANDARD,
        progress=progress,
    )


@dataclass
class AiExportResult:
    bundle: dict
    zip_bytes: bytes
    as_of: str
    run_id: str | None


def run_ai_export(data_dir: Path, output_dir: Path) -> AiExportResult:
    """AI 교차 검증용 번들·ZIP 생성 — bundle_only (no full recalculation)."""
    from src.runtime.pipeline_runner import run_bundle_only

    result = run_bundle_only(data_dir, output_dir, create_zip=True)
    from src.report.io_utils import read_output_json

    bundle = read_output_json(output_dir / "ai_export_bundle.json") or {}
    from src.validation.ai_export import build_export_zip

    zip_bytes = build_export_zip(bundle)
    return AiExportResult(
        bundle=bundle,
        zip_bytes=zip_bytes,
        as_of=str(bundle.get("as_of", "")),
        run_id=bundle.get("run_id"),
    )
