"""오늘 해부 2~3종 루프."""

from __future__ import annotations

from alpha_system.ui.services.gieop_alpha_seed import SRC_SOFT_VALUE, SRC_VALUE, AlphaGieopCandidate
from alpha_system.ui.services.gieop_fusion_desk import FusionRow, QuantCover, build_quant_cover
from alpha_system.ui.services.gieop_today_loop import (
    build_today_gieop_loop,
    today_gieop_loop_html,
)


def test_today_loop_picks_at_most_three() -> None:
    class _V:
        per = 10.0
        pbr = 0.9
        roe = 12.0
        pass_absolute = True
        pass_sector_rel = True
        pass_quality = True
        crash_flag = False
        market_cap = 1e12
        evidence_ok = False

    q = build_quant_cover(in_soft=True, pass_value=True, value_row=_V())
    rows = [
        FusionRow(
            ticker="111770",
            name="영원무역",
            source_ko="Soft∩논리가치",
            in_soft=True,
            pass_value=True,
            draft=None,
            quant=q,
        ),
        FusionRow(
            ticker="073240",
            name="금호타이어",
            source_ko="Soft∩논리가치",
            in_soft=True,
            pass_value=True,
            draft=None,
            quant=q,
        ),
        FusionRow(
            ticker="005380",
            name="현대차",
            source_ko="논리가치만",
            in_soft=False,
            pass_value=True,
            draft=None,
            quant=build_quant_cover(in_soft=False, pass_value=True, value_row=_V()),
        ),
        FusionRow(
            ticker="105560",
            name="KB금융",
            source_ko="논리가치만",
            in_soft=False,
            pass_value=True,
            draft=None,
            quant=build_quant_cover(in_soft=False, pass_value=True, value_row=_V()),
        ),
    ]
    board = build_today_gieop_loop(
        market="KOSPI",
        fusion_rows=rows,
        candidates=[
            AlphaGieopCandidate(
                "111770", "영원무역", "유통", SRC_SOFT_VALUE, "", True, False, True
            ),
            AlphaGieopCandidate(
                "073240", "금호타이어", "화학", SRC_SOFT_VALUE, "", True, False, True
            ),
            AlphaGieopCandidate(
                "005380", "현대차", "자동차", SRC_VALUE, "", False, False, True
            ),
            AlphaGieopCandidate(
                "105560", "KB금융", "은행", SRC_VALUE, "", False, False, True
            ),
        ],
        max_picks=3,
    )
    assert 1 <= len(board.picks) <= 3
    assert board.picks[0].in_soft is True
    html = today_gieop_loop_html(board)
    assert "오늘 해부" in html
    assert "pf-today-gieop" in html
    assert board.writes_target is False
