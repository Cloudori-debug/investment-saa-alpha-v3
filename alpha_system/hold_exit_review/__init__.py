"""Parallel edition: value hold / exit lifecycle (Review-only).

Default dashboard (alpha_dashboard.py) does not import this package.
Run alpha_dashboard_hold_exit.py instead.
"""

from alpha_system.hold_exit_review.config import HoldExitReviewConfig, load_hold_exit_config

__all__ = ["HoldExitReviewConfig", "load_hold_exit_config"]
