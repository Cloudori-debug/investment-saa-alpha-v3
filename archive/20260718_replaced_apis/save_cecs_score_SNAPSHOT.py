# Archived from cecs_workbench.py (2026-07-18)
def save_cecs_score(
    *,
    path: Path,
    ticker: str,
    execution: float,
    execution_rationale: str,
    pension: float,
    pension_rationale: str,
    purpose: float,
    purpose_rationale: str,
    status: ScoreStatus,
    scored_by: str,
    as_of: date,
    journal_path: Path | None = None,
) -> CecsSaveResult:
    """Update one existing template row while preserving schema and row order."""
    values = {
        "execution_continuity": float(execution),
        "pension_flow_score": float(pension),
        "investment_purpose_flag": float(purpose),
    }
    for key, value in values.items():
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{key}는 0.0~1.0이어야 합니다.")

    rationales = {
        "execution_rationale": execution_rationale.strip(),
        "pension_rationale": pension_rationale.strip(),
        "investment_purpose_rationale": purpose_rationale.strip(),
    }
    if status == "final":
        missing = [key for key, value in rationales.items() if not value]
        if missing:
            raise ValueError(
                "채점 완료에는 execution/pension/purpose 근거 3개가 모두 필요합니다."
            )
    if not scored_by.strip():
        raise ValueError("채점자 이름이 필요합니다.")

    with _WRITE_LOCK:
        frame = load_cecs_template(path)
        ticker_n = _ticker(ticker)
        hits = frame.index[frame["ticker"] == ticker_n].tolist()
        if len(hits) != 1:
            raise ValueError(f"CECS template에서 {ticker_n} 단일 행을 찾을 수 없습니다.")
        idx = hits[0]

        policy = _float_or_default(frame.at[idx, "policy_dependency_flag"], 0.5)
        cecs = calculate_cecs(
            CatalystInputs(
                ticker=ticker_n,
                name=str(frame.at[idx, "name"]),
                execution_continuity=values["execution_continuity"],
                pension_flow_score=values["pension_flow_score"],
                investment_purpose_flag=values["investment_purpose_flag"],
                policy_dependency_flag=policy,
            )
        )
        for key, value in values.items():
            frame.at[idx, key] = f"{value:.2f}"
        for key, value in rationales.items():
            frame.at[idx, key] = value
        frame.at[idx, "cecs_computed"] = f"{cecs:.2f}"
        frame.at[idx, "scored_by"] = scored_by.strip()
        frame.at[idx, "scored_at"] = as_of.isoformat()
        frame.at[idx, "status"] = status
        _atomic_csv_write(frame, path)

    progress = cecs_progress(path)
    if status == "final":
        append_record(
            action_kind="CECS_SCORE_FINALIZED",
            as_of=as_of,
            subject=ticker_n,
            rationale="CECS 3축 채점 완료 (근거 3건 확인)",
            score_snapshot={
                **values,
                "cecs": cecs,
            },
            payload={
                "scored_by": scored_by.strip(),
                "final": progress.final,
                "total": progress.total,
            },
            journal_path=journal_path,
        )
    return CecsSaveResult(
        ticker=ticker_n,
        status=status,
        cecs=cecs,
        final=progress.final,
        total=progress.total,
    )

