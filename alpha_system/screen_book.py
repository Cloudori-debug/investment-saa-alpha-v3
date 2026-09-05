"""Independent KOSPI / KOSDAQ screen books.

Same engine, separate ledgers. Never mix markets in one collect pass.
KOSPI keeps the existing data/ tree so the live book is not migrated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

Market = Literal["KOSPI", "KOSDAQ"]

MARKETS: tuple[Market, ...] = ("KOSPI", "KOSDAQ")
DEFAULT_MARKET: Market = "KOSPI"

KOSDAQ_TARGET_NAMES = 3
KOSDAQ_MAX_PER_SECTOR = 1
KOSDAQ_WATCH_MAX = 10
KOSDAQ_LIQUID_MAX = 80
KOSDAQ_CAP_MIN = 200_000_000_000  # 2,000억 — DART 상한 전에 절대 바닥
KOSDAQ_SECTOR_TOP_N = 4  # 업종마다 시총 상위 N · 그 다음 80종 상한

_POSITIONS_HEADER = (
    "ticker,name,asset_group,sector,style,quantity,current_value,avg_price,current_price\n"
)
_TARGET_HEADER = (
    "ticker,name,asset_group,sector,role,target_weight,min_weight,max_weight\n"
)


def normalize_market(raw: object) -> Market:
    text = str(raw or "").strip().upper()
    if text in {"KOSDAQ", "코스닥"}:
        return "KOSDAQ"
    return "KOSPI"


def is_kosdaq(market: object) -> bool:
    return normalize_market(market) == "KOSDAQ"


def market_label(market: object) -> str:
    return "코스닥" if is_kosdaq(market) else "코스피"


def operational_data_dir(root: Path, market: object | None = None) -> Path:
    root = Path(root)
    if is_kosdaq(market):
        return root / "data" / "books" / "kosdaq"
    return root / "data"


def alpha_data_dir(root: Path, market: object | None = None) -> Path:
    root = Path(root)
    if is_kosdaq(market):
        return root / "alpha_portfolio" / "data" / "books" / "kosdaq"
    return root / "alpha_portfolio" / "data"


def quality_fundamentals_csv(root: Path, market: object | None = None) -> Path:
    """Collect-time fundamentals (ROE) used to score alpha_scores — not ops ledger."""
    return alpha_data_dir(root, market) / "raw" / "fundamentals.csv"


def resolve_quality_fundamentals_csv(ops_data_dir: Path | None) -> Path | None:
    """Map an ops ledger folder to the matching alpha collect fundamentals file."""
    if ops_data_dir is None:
        return None
    ops = Path(ops_data_dir)
    if ops.name == "kosdaq" and ops.parent.name == "books":
        return quality_fundamentals_csv(ops.parent.parent.parent, "KOSDAQ")
    if ops.name == "data":
        return quality_fundamentals_csv(ops.parent, "KOSPI")
    return None


def provenance_rel(market: object | None = None) -> Path:
    if is_kosdaq(market):
        return Path("data") / "books" / "kosdaq" / "alpha_quant_snapshot_provenance.json"
    return Path("data") / "alpha_quant_snapshot_provenance.json"


def watch_max(market: object | None = None) -> int:
    return KOSDAQ_WATCH_MAX if is_kosdaq(market) else 30


def target_names_band(market: object | None = None) -> tuple[int, int, int]:
    """(min, max, default) for the portfolio size radio."""
    if is_kosdaq(market):
        return (3, 3, KOSDAQ_TARGET_NAMES)
    return (5, 8, 6)


def load_kosdaq_policy(root: Path) -> dict[str, Any]:
    path = operational_data_dir(root, "KOSDAQ") / "book_policy.yaml"
    if not path.exists():
        return {}
    try:
        import yaml

        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def save_kosdaq_policy(
    root: Path, *, cutoff: float, target_names: int
) -> Path:
    data = ensure_book_dirs(root, "KOSDAQ")
    path = data / "book_policy.yaml"
    names = int(target_names)
    path.write_text(
        (
            f"score_cutoff: {float(cutoff):g}\n"
            f"target_names: {names}\n"
            f"max_names_per_sector: {KOSDAQ_MAX_PER_SECTOR}\n"
        ),
        encoding="utf-8",
    )
    return path


def apply_book_config(cfg: Any, market: object | None = None, *, root: Path | None = None) -> Any:
    if not is_kosdaq(market):
        return cfg
    policy = load_kosdaq_policy(root) if root is not None else {}
    names = int(policy.get("target_names") or KOSDAQ_TARGET_NAMES)
    per_sector = int(policy.get("max_names_per_sector") or KOSDAQ_MAX_PER_SECTOR)
    scoring = cfg.scoring
    if "score_cutoff" in policy and policy.get("score_cutoff") is not None:
        scoring = scoring.model_copy(
            update={"score_cutoff": float(policy["score_cutoff"])}
        )
    else:
        scoring = scoring.model_copy(update={"score_cutoff": None})
    return cfg.model_copy(
        update={
            "universe": cfg.universe.model_copy(
                update={
                    "include_markets": ["KOSDAQ"],
                    "gate_config_path": "data/books/kosdaq/universe_filter.yaml",
                }
            ),
            "scoring": scoring,
            "sizing": cfg.sizing.model_copy(
                update={
                    "target_names": names,
                    "max_names_per_sector": per_sector,
                }
            ),
            "benchmark": "KOSDAQ",
        }
    )


def ensure_book_dirs(root: Path, market: object | None = None) -> Path:
    """Create the KOSDAQ ledger folders. KOSPI already lives in data/."""
    root = Path(root)
    if not is_kosdaq(market):
        return operational_data_dir(root, market)
    data = operational_data_dir(root, "KOSDAQ")
    alpha = alpha_data_dir(root, "KOSDAQ")
    for folder in (data, alpha / "raw", alpha / "input", alpha / "output", alpha / "state"):
        folder.mkdir(parents=True, exist_ok=True)
    positions = data / "positions.csv"
    if not positions.exists():
        positions.write_text(_POSITIONS_HEADER, encoding="utf-8")
    targets = data / "target_portfolio.csv"
    if not targets.exists():
        targets.write_text(_TARGET_HEADER, encoding="utf-8")
    exit_yaml = data / "kr_alpha_exit_targets.yaml"
    if not exit_yaml.exists():
        exit_yaml.write_text("tickers: {}\n", encoding="utf-8")
    return data
