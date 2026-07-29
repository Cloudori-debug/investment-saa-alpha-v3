"""Alpha book ops policy — literature-aligned Review-only operating rules.

SAA (ETF fixed ratios) is out of scope. Alpha book = equity 90% + KODEX
단기채권PLUS 10%, 9 names equal-weight, regime only scales cash guidance,
never rewrites target_portfolio.csv.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

DEFAULT_POLICY_REL = Path("data") / "alpha_book_ops.yaml"


@dataclass(frozen=True)
class AlphaBookOpsPolicy:
    equity_share: float
    cash_share: float
    cash_ticker: str
    cash_name: str
    target_names: int
    equity_weight_mode: str
    band_rel: float
    exclude_zero_qty: bool
    regime_cash_guidance: dict[str, float]
    signal_priority: tuple[str, ...]
    raw: dict[str, Any]

    @property
    def equity_per_name(self) -> float:
        n = max(1, int(self.target_names))
        return float(self.equity_share) / n

    def cash_guidance_for_regime(self, regime_label: str) -> float:
        raw = (regime_label or "").upper()
        table = self.regime_cash_guidance
        for key, frac in table.items():
            if key == "default":
                continue
            if key.upper() in raw:
                return float(frac)
        return float(table.get("default", self.cash_share))


def load_alpha_book_ops(root: Path | None = None) -> AlphaBookOpsPolicy:
    root = Path(root) if root else Path(".")
    path = root / DEFAULT_POLICY_REL
    data: dict[str, Any] = {}
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    book = data.get("book") or {}
    guidance = data.get("regime_cash_guidance") or {}
    priority = data.get("signal_priority") or []
    return AlphaBookOpsPolicy(
        equity_share=float(book.get("equity_share", 0.90)),
        cash_share=float(book.get("cash_share", 0.10)),
        cash_ticker=str(book.get("cash_ticker", "214980")).zfill(6),
        cash_name=str(book.get("cash_name", "KODEX 단기채권PLUS")),
        target_names=int(book.get("target_names", 9)),
        equity_weight_mode=str(book.get("equity_weight_mode", "equal")),
        band_rel=float(book.get("band_rel", 0.25)),
        exclude_zero_qty=bool(book.get("exclude_zero_qty", True)),
        regime_cash_guidance={str(k): float(v) for k, v in guidance.items()},
        signal_priority=tuple(str(x) for x in priority),
        raw=data,
    )


def equal_equity_weights(n: int, *, equity_share: float) -> float:
    """Per-name weight as fraction of alpha book (0–1)."""
    if n <= 0:
        return 0.0
    return float(equity_share) / int(n)


def alpha_target_map_from_saa_csv(
    saa_kr_alpha: Mapping[str, tuple[str, float]],
    policy: AlphaBookOpsPolicy,
) -> dict[str, tuple[str, float]]:
    """Convert SAA-relative kr_alpha targets → alpha-book % (equity + cash = 100)."""
    out: dict[str, tuple[str, float]] = {}
    equity_budget = policy.equity_share * 100.0
    cash_pct = round(policy.cash_share * 100.0, 2)

    if not saa_kr_alpha:
        out[policy.cash_ticker] = (policy.cash_name, cash_pct)
        return out

    raw = {tk: max(0.0, float(w)) for tk, (_, w) in saa_kr_alpha.items()}
    total = sum(raw.values()) or 1.0
    if policy.equity_weight_mode == "equal":
        n = len(raw)
        each = equity_budget / n if n else 0.0
        for tk, (name, _) in saa_kr_alpha.items():
            out[tk] = (name, round(each, 2))
    else:
        for tk, (name, w) in saa_kr_alpha.items():
            out[tk] = (name, round(equity_budget * (w / total), 2))

    out[policy.cash_ticker] = (policy.cash_name, cash_pct)
    s = sum(v for _, v in out.values())
    if abs(s - 100.0) > 0.05 and out:
        drift = round(100.0 - s, 2)
        # Prefer adjusting cash so equity slots stay equal
        name_c, w_c = out[policy.cash_ticker]
        out[policy.cash_ticker] = (name_c, round(w_c + drift, 2))
    return out


def _row_qty(r: Any) -> float | None:
    qty = getattr(r, "quantity", None)
    if qty is not None:
        try:
            return float(qty)
        except (TypeError, ValueError):
            return None
    extra = getattr(r, "extra", None) or {}
    if isinstance(extra, dict) and "quantity" in extra:
        try:
            return float(extra["quantity"])
        except (TypeError, ValueError):
            return None
    return None


def _row_value(r: Any) -> float:
    for attr in ("current_value", "market_value"):
        v = getattr(r, attr, None)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    extra = getattr(r, "extra", None) or {}
    if isinstance(extra, dict):
        for key in ("current_value", "market_value"):
            if key in extra:
                try:
                    return float(extra[key])
                except (TypeError, ValueError):
                    pass
    w = getattr(r, "weight_pct", None)
    try:
        return float(w) if w is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def build_alpha_actual_map(
    root: Path,
    ops_rows: Sequence[Any],
    policy: AlphaBookOpsPolicy,
) -> dict[str, tuple[float, str]]:
    """Alpha-book actual % (sum≈100) from live positions + ops names.

    Includes cash_ticker from positions.csv when held. Drops qty/value 0 ghosts.
    """
    values: dict[str, float] = {}
    names: dict[str, str] = {}

    pos_path = Path(root) / "data" / "positions.csv"
    if pos_path.exists():
        try:
            import pandas as pd

            pdf = pd.read_csv(pos_path, dtype=str)
            if not pdf.empty and "ticker" in pdf.columns:
                for _, row in pdf.iterrows():
                    tk = str(row.get("ticker") or "").zfill(6)
                    if not tk or tk == "000000":
                        continue
                    grp = str(row.get("asset_group") or "")
                    is_cash = tk == policy.cash_ticker
                    is_alpha = grp == "kr_alpha"
                    if not (is_cash or is_alpha):
                        continue
                    try:
                        qty = float(row.get("quantity") or 0)
                    except (TypeError, ValueError):
                        qty = 0.0
                    try:
                        cur = float(row.get("current_value") or 0)
                    except (TypeError, ValueError):
                        cur = 0.0
                    if policy.exclude_zero_qty and qty <= 0 and cur <= 0:
                        continue
                    if cur <= 0 and qty <= 0:
                        continue
                    values[tk] = values.get(tk, 0.0) + max(0.0, cur)
                    names[tk] = str(row.get("name") or tk)
        except Exception:
            pass

    # Fallback: ops sleeve weights when positions empty of alpha value
    if not values:
        for r in ops_rows or []:
            tk = str(getattr(r, "ticker", "") or "").zfill(6)
            if not tk:
                continue
            qty = _row_qty(r)
            val = _row_value(r)
            if policy.exclude_zero_qty:
                if qty is not None and qty <= 0 and val <= 1e-9:
                    continue
                if qty is None and val <= 1e-9:
                    continue
            values[tk] = max(0.0, val)
            names[tk] = str(getattr(r, "name", None) or tk)

    total = sum(values.values())
    if total <= 1e-12:
        return {}
    return {
        tk: (round(100.0 * v / total, 2), names.get(tk, tk))
        for tk, v in values.items()
    }


def guidance_rows(
    policy: AlphaBookOpsPolicy, regime_label: str
) -> list[dict[str, str]]:
    """Home / rebal caption table."""
    cash_g = policy.cash_guidance_for_regime(regime_label)
    equity_g = max(0.0, 1.0 - cash_g)
    per = equity_g / max(1, policy.target_names)
    return [
        {
            "항목": "알파북 기본",
            "내용": (
                f"개별주 {policy.equity_share * 100:.0f}% "
                f"({policy.target_names}종×"
                f"{policy.equity_per_name * 100:.1f}%) · "
                f"{policy.cash_name} {policy.cash_share * 100:.0f}%"
            ),
        },
        {
            "항목": "오늘 단기채 가이던스",
            "내용": (
                f"{cash_g * 100:.0f}% ({policy.cash_ticker}) · "
                f"개별주 합 {equity_g * 100:.0f}% "
                f"(종목당≈{per * 100:.1f}%) · Review-only · target 불변"
            ),
        },
        {
            "항목": "신호 우선",
            "내용": "전량·환금·줄이기 → 밴드 축소 → 모멘텀 축소 → 편입·분할매수",
        },
        {
            "항목": "불변",
            "내용": "Core 순위 레짐/모멘텀 비변경 · 자동매매 없음 · target 사람만",
        },
    ]
