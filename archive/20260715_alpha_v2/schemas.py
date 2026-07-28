from __future__ import annotations

ALPHA_V2_SCHEMA = "alpha_v2_shadow_mvp"
ALPHA_V2_MODE = "shadow"

POLICY_NOTES: list[str] = [
    "Alpha v2 is shadow-only.",
    "Flow signal is not buy permission.",
    "Actual Buy Allowed=0 overrides all buy triggers.",
    "NO_TRADE means review-only.",
    "candidate only, not buy approval",
    "KOSDAQ candidates are shadow/review-only until separately approved.",
    "KOSDAQ Shadow Watch is not buy permission.",
    "Actual Buy Allowed=0 overrides all KOSDAQ signals.",
    "KOSDAQ single suggested_shadow_weight is capped below KOSPI; sleeve max 30%.",
]

CANDIDATE_ONLY_NOTE = "candidate only, not buy approval"

# Grade thresholds on total_score_v1 (operational grade — flow does not upgrade Reject)
GRADE_A_MIN = 75.0
GRADE_B_MIN = 60.0
GRADE_C_MIN = 45.0
GRADE_D_MIN = 30.0

FLOW_SCORE_MIN = -20.0
FLOW_SCORE_MAX = 20.0

FINAL_MIN = 5
FINAL_MAX = 8
TOP30_MAX = 30
KOSPI_FINAL_MIN = 3
KOSPI_FINAL_MAX = 5
KOSDAQ_FINAL_MIN = 1
KOSDAQ_FINAL_MAX = 3
SECTOR_CAP_PCT = 30.0
KOSPI_SINGLE_WEIGHT_MAX = 8.0
KOSDAQ_SINGLE_WEIGHT_MAX = 4.0
KOSDAQ_SLEEVE_MAX_PCT = 30.0

FLOW_SIGNAL_STATES = frozenset({
    "accumulation",
    "distribution",
    "co_buy",
    "co_sell",
    "turning_buy",
    "turning_sell",
    "neutral",
    "stale",
})
