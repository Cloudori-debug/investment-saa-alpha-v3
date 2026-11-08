"""Mid-book shadow profit machine — Review-only proof loop.

Never writes target_portfolio.csv or places broker orders.
"""

from alpha_system.shadow.mid_book import ShadowBookState, apply_ops_to_weights, step_day
from alpha_system.shadow.mid_ledger import (
    ledger_path,
    load_ledger,
    append_day,
    summarize_ledger,
)
from alpha_system.shadow.report import shadow_report_dict, shadow_card_html
from alpha_system.shadow.rotation_coverage import (
    summarize_rotation,
    rotation_log_path,
    load_rotation_events,
)
from alpha_system.shadow.l3_crash_backtest import (
    run_l3_crash_backtest,
    report_card_html as l3_backtest_card_html,
)
from alpha_system.shadow.fear_soft_rebal_backtest import (
    run_fear_soft_rebal_backtest,
    fear_soft_card_html,
)
from alpha_system.shadow.proposal_price_replay import (
    run_proposal_price_replay,
    replay_ledger_path,
)

__all__ = [
    "ShadowBookState",
    "apply_ops_to_weights",
    "step_day",
    "ledger_path",
    "load_ledger",
    "append_day",
    "summarize_ledger",
    "shadow_report_dict",
    "shadow_card_html",
    "summarize_rotation",
    "rotation_log_path",
    "load_rotation_events",
    "run_l3_crash_backtest",
    "l3_backtest_card_html",
    "run_fear_soft_rebal_backtest",
    "fear_soft_card_html",
    "run_proposal_price_replay",
    "replay_ledger_path",
]
