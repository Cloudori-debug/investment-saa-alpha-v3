"""경제 나침반 입력 묶음 갱신 — FRED 국면 + market_indicators (Review-only).

Fear&Greed Soft·평균회귀·단기 변동 Soft가 ``data/market_indicators.csv`` 에
의존하는데, 나침반「다시 계산」이 FRED만 돌리면 VIX·코스피가 수개월 정체한다.
target·QVM·Core score_m 불변.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class CompassInputsRefreshResult:
    ok: bool
    detail: str = ""
    economy_fetched_at: str = ""
    market_as_of: str = ""
    market_updated: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    writes_target: bool = False


def market_indicators_as_of(root: Path) -> str:
    path = Path(root) / "data" / "market_indicators.csv"
    if not path.is_file():
        return ""
    try:
        import pandas as pd

        df = pd.read_csv(path, dtype=str)
        if df.empty:
            return ""
        return str(df.iloc[-1].get("date") or "").strip()
    except (OSError, ValueError):
        return ""


def market_indicators_stale_days(root: Path, *, today: str | None = None) -> int | None:
    """Latest market_indicators date age in calendar days · None if unknown."""
    as_of = market_indicators_as_of(root)
    if not as_of:
        return None
    try:
        d0 = datetime.strptime(as_of[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    if today:
        try:
            d1 = datetime.strptime(str(today)[:10], "%Y-%m-%d").date()
        except ValueError:
            d1 = datetime.now(timezone.utc).date()
    else:
        d1 = datetime.now(timezone.utc).date()
    return max(0, (d1 - d0).days)


def refresh_compass_inputs(
    root: Path,
    *,
    refresh_market: bool = True,
    refresh_fred: bool = True,
) -> CompassInputsRefreshResult:
    """FRED + (optional) market_indicators · compass snapshot · no target."""
    root = Path(root)
    warnings: list[str] = []
    errors: list[str] = []
    economy_at = ""
    market_as_of = ""
    market_updated: list[str] = []

    if refresh_fred:
        try:
            from alpha_system.economy_compass import build_compass, save_compass_snapshot
            from alpha_system.economy_signal import refresh_economy_signal

            signal = refresh_economy_signal(root, api_key="")
            economy_at = str(getattr(signal, "fetched_at", "") or "")
            save_compass_snapshot(root, build_compass(signal))
            if not getattr(signal, "known", 0) and getattr(signal, "detail", ""):
                warnings.append(str(signal.detail)[:160])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"FRED 국면: {exc}"[:200])

    if refresh_market:
        try:
            from src.data_refresh.market_indicators_refresh import (
                refresh_all_market_indicators,
            )

            try:
                mi = refresh_all_market_indicators(
                    root / "data",
                    as_of=None,
                    use_pykrx=True,
                    use_external=True,
                )
            except Exception as exc_full:  # noqa: BLE001
                # KRX 비번/세션 실패 시에도 VIX·S&P는 외부로 갱신
                warnings.append(f"PyKRX 포함 갱신 실패 → 외부만: {exc_full}"[:160])
                mi = refresh_all_market_indicators(
                    root / "data",
                    as_of=None,
                    use_pykrx=False,
                    use_external=True,
                )
            market_as_of = str(mi.as_of or "")
            market_updated = list(mi.updated_fields or [])
            warnings.extend(str(w)[:160] for w in (mi.warnings or [])[:8])
            errors.extend(str(e)[:160] for e in (mi.errors or [])[:6])
            if not market_updated and not market_as_of:
                errors.append("market_indicators 갱신 필드 없음")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"market_indicators: {exc}"[:200])

    ok = not errors or bool(economy_at or market_as_of)
    bits = []
    if economy_at:
        bits.append("FRED 국면")
    if market_as_of:
        bits.append(f"시장지표 {market_as_of}")
    if errors and not bits:
        detail = " · ".join(errors[:2])
        ok = False
    elif errors:
        detail = (bits and " · ".join(bits) + " · " or "") + f"경고 {len(errors)}"
    else:
        detail = " · ".join(bits) if bits else "갱신 없음"

    result = CompassInputsRefreshResult(
        ok=ok,
        detail=detail,
        economy_fetched_at=economy_at,
        market_as_of=market_as_of or market_indicators_as_of(root),
        market_updated=market_updated,
        warnings=warnings,
        errors=errors,
        writes_target=False,
    )
    try:
        from alpha_system.ui.services.data_fetch_alerts import (
            record_from_compass_bundle,
        )

        record_from_compass_bundle(root, result)
    except Exception:  # noqa: BLE001
        pass
    return result


def maybe_refresh_compass_inputs_after_quant(
    root: Path,
    *,
    force: bool = False,
    max_age_days: int = 1,
) -> dict[str, Any]:
    """확인① 후 · 시장지표가 하루 이상 오래되면 나침반 입력 묶음 갱신."""
    root = Path(root)
    age = market_indicators_stale_days(root)
    if not force and age is not None and age < int(max_age_days):
        return {
            "ok": True,
            "skipped": True,
            "reason": "fresh",
            "market_as_of": market_indicators_as_of(root),
            "stale_days": age,
            "writes_target": False,
        }
    result = refresh_compass_inputs(root, refresh_market=True, refresh_fred=True)
    return {
        "ok": result.ok,
        "skipped": False,
        "detail": result.detail,
        "market_as_of": result.market_as_of,
        "economy_fetched_at": result.economy_fetched_at,
        "warnings": result.warnings[:5],
        "errors": result.errors[:5],
        "writes_target": False,
    }


__all__ = [
    "CompassInputsRefreshResult",
    "market_indicators_as_of",
    "market_indicators_stale_days",
    "maybe_refresh_compass_inputs_after_quant",
    "refresh_compass_inputs",
]
