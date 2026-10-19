"""Review-only evaluation helpers (no target_portfolio / QVM writes)."""

__all__ = [
    "MODEL_VERSION",
    "evaluate_phcvs",
    "entry_price_ceiling",
    "run_and_write",
]


def __getattr__(name: str):
    if name in __all__:
        from alpha_system.review import phcvs_auto_eval as _m

        return getattr(_m, name)
    raise AttributeError(name)
