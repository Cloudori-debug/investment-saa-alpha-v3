"""Home pipeline stage cards — lock reasons and deep links."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from alpha_system.loader import load_config
from alpha_system.ui.services.context import ScoreboardRow
from alpha_system.ui.services.data_freshness import SourceStatus
from alpha_system.ui.services.home_pipeline import (
    build_home_overview,
    build_pipeline_stages,
    first_blocker,
)
from alpha_system.ui.services.nav import PAGE_CECS


def _ctx(**overrides):
    cfg = load_config()
    base = dict(
        root=Path("."),
        cfg=cfg,
        as_of=date.today(),
        pre_launch=True,
        effective_go_live=None,
        cecs_final_count=30,
        cecs_total=30,
        proposal_count=0,
        held_kr_alpha=0,
        scoreboard_rows=[],
        portfolio_rows=[],
        source_status=[
            SourceStatus(
                key="alpha_scores",
                label="alpha_scores",
                path="alpha_portfolio/data/output/alpha_scores.csv",
                as_of=date.today(),
                recommended_days=7,
                stale=False,
                exists=True,
            )
        ],
        checklist=SimpleNamespace(blocking=[]),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_cutoff_mismatch_is_first_blocker() -> None:
    rows = [
        ScoreboardRow(
            ticker="005830",
            name="DB",
            total_score=64.0,
            score_q=60,
            score_v=60,
            score_sr=60,
            score_r=60,
            cecs=70,
            eligibility=False,
            sector_peer_fallback=False,
            is_held=False,
            status="final",
        )
    ]
    cfg = load_config()
    cfg = cfg.model_copy(
        update={"scoring": cfg.scoring.model_copy(update={"score_cutoff": 86.33})}
    )
    ctx = _ctx(cfg=cfg, scoreboard_rows=rows, proposal_count=0)
    stages = build_pipeline_stages(ctx)
    blocker = first_blocker(stages)
    assert blocker is not None
    assert blocker.key == "cutoff"
    assert blocker.page == PAGE_CECS
    assert "적격 0" in blocker.reason


def test_cecs_incomplete_does_not_block_pipeline() -> None:
    """Ops A: incomplete CECS is advisory warn, not a hard blocker."""
    cfg = load_config()
    cfg = cfg.model_copy(
        update={"scoring": cfg.scoring.model_copy(update={"score_cutoff": 60.0})}
    )
    ctx = _ctx(cfg=cfg, cecs_final_count=10, cecs_total=30, proposal_count=0)
    stages = build_pipeline_stages(ctx)
    cecs_stage = next(s for s in stages if s.key == "cecs")
    assert cecs_stage.status == "warn"
    assert cecs_stage.blocks_next is False
    blocker = first_blocker(stages)
    assert blocker is None or blocker.key != "cecs"


def test_home_overview_shows_only_quant_action_first(tmp_path: Path) -> None:
    stale = SourceStatus(
        key="alpha_scores",
        label="alpha_scores",
        path="alpha_scores.csv",
        as_of=date(2026, 6, 1),
        recommended_days=7,
        stale=True,
        exists=True,
    )
    ctx = _ctx(root=tmp_path, source_status=[stale])
    overview = build_home_overview(ctx)
    assert len(overview.preparation) == 2
    assert overview.preparation[0].status == "warn"
    assert overview.preparation[1].status == "missing"
    assert overview.next_action is not None
    assert overview.next_action.key == "quant"


def test_home_overview_routes_uploaded_report_to_one_approval_action(
    tmp_path: Path,
) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "weekly_qual_suggestions.json").write_text(
        """
{
  "as_of": "2026-07-17",
  "domain_status": {
    "cecs": "ai_suggested",
    "t2": "ai_suggested",
    "thesis": "approved",
    "targets": "approved"
  },
  "approved": {
    "cecs": false,
    "t2": false,
    "thesis": true,
    "targets": true
  }
}
""".strip(),
        encoding="utf-8",
    )
    ctx = _ctx(root=tmp_path)
    overview = build_home_overview(ctx)
    assert overview.pending_approvals == 2
    assert overview.preparation[1].status == "warn"
    assert overview.next_action is not None
    assert overview.next_action.key == "weekly_approve"
    assert "2영역" in overview.next_action.reason
