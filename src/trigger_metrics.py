"""Unified watch-trigger counting for reports and shadow diagnostic."""
from __future__ import annotations

from src.models import TriggerAlert, TriggerStatus

_ASSET_KEY_TO_GROUP: dict[str, str] = {
    "domestic_beta": "domestic_beta",
    "global_beta": "global_beta",
    "sk_hynix": "kr_alpha",
    "gold": "hedge_alt",
    "dollar": "fx_dollar",
}


def _is_buy_watch_key(key: str) -> bool:
    k = key.lower()
    return "buy" in k or "pullback" in k


def _asset_group_for_buy_key(key: str) -> str | None:
    if not key.startswith("asset_buy_"):
        return None
    asset = key.replace("asset_buy_", "", 1)
    return _ASSET_KEY_TO_GROUP.get(asset, asset)


def is_zero_target_suppressed(
    alert: TriggerAlert,
    asset_group_gaps: dict[str, dict[str, float]] | None,
) -> bool:
    """Suppress asset-level buy signals when compass target weight is 0%."""
    if not asset_group_gaps:
        return False
    group = _asset_group_for_buy_key(alert.key)
    if not group:
        return False
    tgt = asset_group_gaps.get(group, {}).get("target")
    if tgt is None:
        return False
    return float(tgt) <= 0.01


def list_watch_triggers(
    alerts: list[TriggerAlert],
    asset_group_gaps: dict[str, dict[str, float]] | None = None,
) -> list[str]:
    """Buy/pullback watch signals — excludes zero-target asset buys and non-buy actives."""
    out: list[str] = []
    for alert in alerts:
        if alert.status != TriggerStatus.ACTIVE:
            continue
        if not _is_buy_watch_key(alert.key):
            continue
        if is_zero_target_suppressed(alert, asset_group_gaps):
            continue
        out.append(alert.key)
    return out


def list_suppressed_signals(alerts: list[TriggerAlert]) -> list[str]:
    """Asset buy signals suppressed (e.g. target weight 0%)."""
    return [
        a.key for a in alerts
        if a.status == TriggerStatus.WATCH and "suppressed" in (a.detail or "").lower()
    ]


def list_all_active_triggers(alerts: list[TriggerAlert]) -> list[str]:
    return [a.key for a in alerts if a.status == TriggerStatus.ACTIVE]


def list_risk_reduce_active_triggers(alerts: list[TriggerAlert]) -> list[str]:
    return [
        a.key for a in alerts
        if a.status == TriggerStatus.ACTIVE and "overweight" in a.key.lower()
    ]
