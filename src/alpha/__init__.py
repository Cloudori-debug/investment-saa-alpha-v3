"""KOSPI Alpha Screener — Q/V/M 팩터 스코어링 및 후보 생성."""

__all__ = ["run_alpha_pipeline"]


def __getattr__(name: str):
    if name == "run_alpha_pipeline":
        from src.alpha.alpha_pipeline import run_alpha_pipeline

        return run_alpha_pipeline
    raise AttributeError(name)
