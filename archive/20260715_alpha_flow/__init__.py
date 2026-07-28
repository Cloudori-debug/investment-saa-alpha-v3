"""Alpha flow dashboard — supply/demand analytics (not buy permission)."""

__all__ = [
    "get_flow_dashboard_inputs",
    "load_flow_data",
    "run_flow_dashboard_outputs",
]


def __getattr__(name: str):
    if name == "run_flow_dashboard_outputs":
        from src.alpha_flow.flow_analytics import run_flow_dashboard_outputs
        return run_flow_dashboard_outputs
    if name == "get_flow_dashboard_inputs":
        from src.alpha_flow.flow_service import get_flow_dashboard_inputs
        return get_flow_dashboard_inputs
    if name == "load_flow_data":
        from src.alpha_flow.flow_service import load_flow_data
        return load_flow_data
    raise AttributeError(name)
