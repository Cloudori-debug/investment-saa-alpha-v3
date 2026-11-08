"""Run price + fundamentals refresh on the host PC."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import subprocess
import sys
import time
from typing import Any

from alpha_system.screen_book import normalize_market, provenance_rel

QUANT_PROVENANCE_REL = Path("data") / "alpha_quant_snapshot_provenance.json"
_KST = timezone(timedelta(hours=9))


@dataclass
class RefreshResult:
    ok: bool
    message: str
    detail: dict[str, Any]


def _job_phase(root: Path, phase: str, *, progress: float | None = None) -> None:
    """백그라운드 job일 때만 phase 기록 · UI 인라인 진행도용."""
    try:
        from alpha_system.ui.services.background_job import update_phase

        update_phase(Path(root), phase, progress=progress)
    except Exception:  # noqa: BLE001
        pass


def quant_refresh_when(root: Path, *, market: str | None = None) -> str | None:
    """Last quant snapshot wall time in KST, or None if never run."""
    path = Path(root) / provenance_rel(market)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    generated = str(raw.get("generated_at") or "").strip()
    if generated:
        try:
            dt = datetime.fromisoformat(generated.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(_KST).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass
    as_of = str(raw.get("as_of") or "").strip()[:10]
    return as_of or None


def _is_krx_timeout(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "timed out" in text or "timeout" in text or "data.krx.co.kr" in text


def _format_refresh_error(exc: BaseException) -> str:
    if _is_krx_timeout(exc):
        return (
            "KRX(data.krx.co.kr) 응답 지연·타임아웃입니다. "
            "일시적 장애인 경우가 많으니 1~2분 뒤 다시 시도하세요. "
            "설정 → KRX 테스트로 연결을 확인할 수 있습니다."
        )
    return str(exc)


def _sync_prices_csv_from_snapshot(
    snap_by_ticker: Any,
    dest_path: Path,
) -> int:
    """Write/merge one prices.csv from alpha snapshot index. No KRX."""
    import pandas as pd

    dest = None
    if dest_path.exists():
        try:
            dest = pd.read_csv(dest_path, dtype=str, keep_default_na=False)
        except Exception:
            dest = None
    if dest is None or dest.empty or "ticker" not in dest.columns:
        dest = pd.DataFrame(
            columns=["date", "ticker", "close", "market_cap", "trading_value_20d"]
        )
    else:
        dest["ticker"] = dest["ticker"].astype(str).str.zfill(6)
        for col in ("date", "close", "market_cap", "trading_value_20d"):
            if col not in dest.columns:
                dest[col] = ""

    n = 0
    for idx, row in dest.iterrows():
        t = str(row["ticker"])
        if t not in snap_by_ticker.index:
            continue
        src = snap_by_ticker.loc[t]
        if "as_of" in src.index and str(src["as_of"]).strip():
            dest.at[idx, "date"] = str(src["as_of"])[:10]
        if "close" in src.index and str(src["close"]).strip():
            dest.at[idx, "close"] = src["close"]
        if "market_cap" in src.index and str(src["market_cap"]).strip():
            dest.at[idx, "market_cap"] = src["market_cap"]
        tv = src.get("avg_trading_value_20d")
        if tv is not None and str(tv).strip():
            dest.at[idx, "trading_value_20d"] = tv
        n += 1

    existing = set(dest["ticker"].astype(str)) if "ticker" in dest.columns else set()
    additions: list[dict[str, str]] = []
    for t, src in snap_by_ticker.iterrows():
        if t in existing:
            continue
        additions.append(
            {
                "date": str(src["as_of"])[:10] if "as_of" in src.index else "",
                "ticker": t,
                "close": str(src["close"]) if "close" in src.index else "",
                "market_cap": str(src["market_cap"]) if "market_cap" in src.index else "",
                "trading_value_20d": (
                    str(src["avg_trading_value_20d"])
                    if "avg_trading_value_20d" in src.index
                    else ""
                ),
            }
        )
    if additions:
        dest = pd.concat([dest, pd.DataFrame(additions)], ignore_index=True)
        n += len(additions)
    if n:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest.to_csv(dest_path, index=False, encoding="utf-8-sig")
    return n


def _sync_operational_prices_from_alpha_snapshot(
    root: Path, *, market: str | None = None
) -> int:
    """Copy snapshot into mid + short book prices.csv (한 시장 · 중기·단기 일원화)."""
    import pandas as pd

    from alpha_system.screen_book import (
        alpha_data_dir,
        ensure_book_dirs,
        operational_data_dir,
    )

    snap_path = alpha_data_dir(root, market) / "raw" / "price_snapshot.csv"
    if not snap_path.exists():
        return 0
    try:
        snap = pd.read_csv(snap_path, dtype=str, keep_default_na=False)
    except Exception:
        return 0
    if snap.empty or "ticker" not in snap.columns:
        return 0
    snap["ticker"] = snap["ticker"].astype(str).str.zfill(6)
    by_t = snap.drop_duplicates("ticker", keep="last").set_index("ticker")

    ensure_book_dirs(root, market, "mid")
    ensure_book_dirs(root, market, "short")
    n = 0
    for hz in ("mid", "short"):
        dest = operational_data_dir(root, market, hz) / "prices.csv"
        n += _sync_prices_csv_from_snapshot(by_t, dest)
    # 소스(중기) prices.csv 는 source_data_dir = mid 와 동일 경로(코스피 data/)
    return n


def _sync_operational_fundamentals_from_alpha(
    root: Path, *, market: str | None = None
) -> int:
    """KOSDAQ book only — do not overwrite the live KOSPI bulk fundamentals."""
    from alpha_system.screen_book import (
        alpha_data_dir,
        is_kosdaq,
        operational_data_dir,
    )

    if not is_kosdaq(market):
        return 0
    src = alpha_data_dir(root, market) / "raw" / "fundamentals.csv"
    dest = operational_data_dir(root, market) / "fundamentals.csv"
    if not src.exists():
        return 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(src.read_bytes())
    return 1


def run_data_refresh(data_dir: Path, *, scope: str = "holdings") -> RefreshResult:
    """
    Invoke existing PyKRX bulk collect (prices + fundamentals).
    Runs locally on the machine hosting Streamlit — not a remote API.
    """
    try:
        from src.settings.user_secrets import apply_secrets_to_env
        from src.data_refresh.pykrx_bulk import run_pykrx_bulk_collect
    except ImportError as exc:
        return RefreshResult(
            ok=False,
            message="수집 모듈을 불러올 수 없습니다.",
            detail={"error": str(exc)},
        )

    apply_secrets_to_env(data_dir)
    positions_path = data_dir / "positions.csv"
    if scope == "holdings" and not positions_path.exists():
        return RefreshResult(
            ok=False,
            message=(
                "positions.csv가 없습니다. data/positions.csv를 복구하거나 "
                "보유 목록을 넣은 뒤 다시 시도하세요."
            ),
            detail={"error": "missing_positions_csv", "path": str(positions_path)},
        )

    last_exc: BaseException | None = None
    attempts = 1
    for attempt in range(1, attempts + 1):
        try:
            result = run_pykrx_bulk_collect(
                data_dir,
                scope=scope,
                merge_existing_universe=True,
                write_history=True,
                enrich_dart=True,
            )
            return RefreshResult(
                ok=True,
                message="현재가·펀더멘털 갱신 완료",
                detail={
                    "as_of": getattr(result, "as_of", None),
                    "tickers": getattr(result, "tickers_processed", None),
                    "errors": getattr(result, "errors", None),
                    "attempts": attempt,
                },
            )
        except Exception as exc:
            last_exc = exc
            if attempt < attempts and _is_krx_timeout(exc):
                time.sleep(3 * attempt)
                continue
            break

    assert last_exc is not None
    return RefreshResult(
        ok=False,
        message=_format_refresh_error(last_exc),
        detail={"error": str(last_exc), "attempts": attempts},
    )


def run_quant_snapshot_refresh(
    root: Path,
    *,
    collect_scope: str = "liquid",
    market: str | None = None,
) -> RefreshResult:
    """One KRX pass via alpha collect (liquid). Does not run holdings bulk first.

    OHLCV uses Naver; KRX is market-wide cap/fundamentals only. No
    target_portfolio writer. Blocked while weekly proposal freeze is active.
    """
    from alpha_system.ui.services.proposal_freeze import (
        assert_quant_refresh_allowed,
        block_message,
        is_freeze_active,
    )

    if is_freeze_active(root):
        try:
            assert_quant_refresh_allowed(root)
        except RuntimeError as exc:
            return RefreshResult(
                ok=False,
                message=str(exc) or block_message(root=root),
                detail={"blocked_by": "weekly_qual_proposal_freeze"},
            )

    script = root / "scripts" / "run_alpha_quant_snapshot.py"
    book = normalize_market(market)
    command = [
        sys.executable,
        str(script),
        "--root",
        str(root),
        "--collect",
        "--collect-scope",
        collect_scope,
        "--market",
        book,
    ]
    _job_phase(root, f"{book} 정량 수집·채점 (KRX·점수)", progress=0.05)
    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return RefreshResult(
            ok=False,
            message=f"정량 스냅샷 실행 실패: {exc}",
            detail={"error": str(exc), "krx_pass": "single"},
        )

    from alpha_system.screen_book import ensure_book_dirs

    _job_phase(root, f"{book} 중기·단기 가격·재무 동기", progress=0.45)
    ensure_book_dirs(root, book, "mid")
    ensure_book_dirs(root, book, "short")
    synced = _sync_operational_prices_from_alpha_snapshot(root, market=book)
    _sync_operational_fundamentals_from_alpha(root, market=book)
    detail: dict[str, Any] = {
        "krx_pass": "single",
        "market": book,
        "horizons": ["mid", "short"],
        "unified_mid_short": True,
        "operational_synced_rows": synced,
        "command": "run_alpha_quant_snapshot.py --collect --collect-scope "
        + collect_scope
        + " --market "
        + book,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "target_portfolio_written": False,
    }
    if completed.returncode != 0:
        return RefreshResult(
            ok=False,
            message="정량 스냅샷 생성 실패",
            detail=detail,
        )

    provenance = root / provenance_rel(book)
    if provenance.exists():
        try:
            detail["provenance"] = json.loads(provenance.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            detail["provenance_path"] = str(provenance)
    scored = int((detail.get("provenance") or {}).get("scored_rows") or 0)
    gate_pass = int((detail.get("provenance") or {}).get("gate_pass") or 0)
    if scored > 0 and gate_pass == 0:
        return RefreshResult(
            ok=False,
            message=(
                "정량 채점은 됐지만 게이트 통과가 0종입니다. "
                "유동성(ADV)·재무·검증 게이트를 확인하세요. "
                "시총 하한은 해제되어 있습니다."
            ),
            detail=detail,
        )
    _job_phase(root, "정성 · RSS·OpenDART·심층·수급", progress=0.55)
    qual = _refresh_qual_layers_after_quant(root, market=book)
    detail["qual_layers"] = qual

    # 가계 ETF Lab — 하루 1회·비치명 · Soft/target 불변 (전략 비교 버튼 최소화)
    _job_phase(root, "가계 ETF Lab (하루 1회)", progress=0.82)
    try:
        from alpha_system.ui.services.ops_journey_chrome import (
            maybe_refresh_household_lab_after_quant,
        )

        hh = maybe_refresh_household_lab_after_quant(root, force=False)
        detail["household_alloc_lab"] = hh
    except Exception as exc:  # noqa: BLE001
        detail["household_alloc_lab_error"] = str(exc)[:200]

    # 나침반 입력(FRED+VIX/코스피) — 시장지표 하루 이상 정체 시 · Soft/target 불변
    _job_phase(root, "나침반 입력 (FRED·시장지표)", progress=0.88)
    try:
        from alpha_system.ui.services.compass_inputs_refresh import (
            maybe_refresh_compass_inputs_after_quant,
        )

        eco = maybe_refresh_compass_inputs_after_quant(root, force=False)
        detail["compass_inputs"] = eco
    except Exception as exc:  # noqa: BLE001
        detail["compass_inputs_error"] = str(exc)[:200]

    # 전략별 투자 후보 스냅샷 (Soft 바스켓 + ETF) · target 불변
    _job_phase(root, "전략 Soft 후보 스냅샷", progress=0.94)
    try:
        from alpha_system.ui.services.strategy_candidates_board import (
            persist_candidates_after_quant,
        )

        cand = persist_candidates_after_quant(root, market=book)
        detail["strategy_candidates"] = cand
    except Exception as exc:  # noqa: BLE001
        detail["strategy_candidates_error"] = str(exc)[:200]
    _job_phase(root, "마무리", progress=0.98)

    hh_bit = ""
    hh = detail.get("household_alloc_lab") or {}
    if isinstance(hh, dict):
        if hh.get("skipped"):
            hh_bit = " · 가계ETF Lab 유지(신선)"
        elif hh.get("ok"):
            hh_bit = f" · 가계ETF Lab {hh.get('n_ok', '')}종"
        elif hh.get("error"):
            hh_bit = " · 가계ETF Lab 생략"
    cand = detail.get("strategy_candidates") or {}
    if isinstance(cand, dict) and cand.get("ok"):
        hh_bit += (
            f" · 후보 Soft중기{cand.get('mid_n', 0)}"
            f"/단기{cand.get('short_n', 0)}"
        )

    return RefreshResult(
        ok=True,
        message=(
            f"{book} 중기·단기 정량·정성 통합 갱신 완료 "
            "(점수 공유 · RSS · OpenDART · 수급 · 가격 mid+short 동기)"
            f"{hh_bit}"
        ),
        detail=detail,
    )


def _watch_pool_tickers(root: Path, *, market: str, top_n: int = 30) -> list[str]:
    """Scoreboard-ranked tickers for OpenDART watch (market book)."""
    from alpha_system.proposal_chart import norm_ticker
    from alpha_system.screen_book import alpha_data_dir, is_kosdaq

    scores_path = alpha_data_dir(root, market) / "output" / "alpha_scores.csv"
    if not scores_path.is_file():
        return []
    try:
        import pandas as pd

        df = pd.read_csv(scores_path)
    except (OSError, ValueError):
        return []
    if df.empty or "ticker" not in df.columns:
        return []
    df = df.copy()
    df["ticker"] = df["ticker"].map(norm_ticker)
    if is_kosdaq(market) and "market" in df.columns:
        m = df["market"].astype(str).str.upper()
        df = df[m.str.contains("KOSDAQ") | m.str.contains("코스닥")]
    elif (not is_kosdaq(market)) and "market" in df.columns:
        m = df["market"].astype(str).str.upper()
        # Prefer KOSPI rows when column exists; else keep all
        kospi = m.str.contains("KOSPI") | m.str.contains("코스피")
        if kospi.any():
            df = df[kospi]
    rank_col = None
    for c in ("total_score", "factor_score_total", "score_q"):
        if c in df.columns:
            rank_col = c
            break
    if rank_col:
        df[rank_col] = pd.to_numeric(df[rank_col], errors="coerce")
        df = df.sort_values(rank_col, ascending=False)
    out: list[str] = []
    seen: set[str] = set()
    for tk in df["ticker"].tolist():
        if not tk or tk in seen:
            continue
        seen.add(tk)
        out.append(tk)
        if len(out) >= int(top_n):
            break
    return out


def watch_pool_tickers(root: Path, *, market: str, top_n: int = 30) -> list[str]:
    """Public: scoreboard top-N for OpenDART / 정성 Review."""
    return _watch_pool_tickers(root, market=market, top_n=top_n)


def ensure_opendart_incremental_if_stale(
    root: Path,
    *,
    market: str,
    top_n: int = 30,
    force: bool = False,
) -> dict[str, Any]:
    """증분 갱신 when stale (or force). Review-only · no target/QVM writes.

    Returns status dict: skipped | refreshed | missing_key | error.
    """
    from alpha_system.screen_book import source_data_dir
    from alpha_system.ui.services.cecs_opendart_pack import (
        load_opendart_watch,
        refresh_opendart_proposal_watch,
        watch_needs_refresh,
    )

    mkt = normalize_market(market) or "KOSPI"
    data_dir = source_data_dir(root, mkt)
    tickers = _watch_pool_tickers(root, market=mkt, top_n=top_n)
    out: dict[str, Any] = {
        "market": mkt,
        "pool_n": len(tickers),
        "mode": "incremental",
        "writes_target": False,
    }
    if not tickers:
        out["status"] = "skipped"
        out["reason"] = "no_watch_tickers"
        return out
    snap = load_opendart_watch(root, data_dir=data_dir)
    stale = watch_needs_refresh(snap, tickers)
    out["stale"] = bool(stale)
    if snap is not None and getattr(snap, "missing_key", False):
        out["status"] = "missing_key"
        out["fetched_at"] = getattr(snap, "fetched_at", "") or ""
        return out
    if not force and not stale:
        out["status"] = "fresh"
        out["fetched_at"] = getattr(snap, "fetched_at", "") or ""
        return out
    try:
        snap = refresh_opendart_proposal_watch(
            root,
            tickers,
            data_dir=data_dir,
            mode="incremental",
            enrich_documents=True,
        )
        out["status"] = "refreshed"
        out["fetched_at"] = getattr(snap, "fetched_at", "") or ""
        out["ticker_n"] = len(getattr(snap, "tickers", ()) or ())
        out["missing_key"] = bool(getattr(snap, "missing_key", False))
        if out["missing_key"]:
            out["status"] = "missing_key"
    except Exception as exc:  # noqa: BLE001
        out["status"] = "error"
        out["error"] = str(exc)[:240]
    return out


def _refresh_qual_layers_after_quant(
    root: Path,
    *,
    market: str,
) -> dict[str, Any]:
    """정성 레이어: 공식 RSS(killswitch) + OpenDART 관찰 풀 증분.

    Never writes target · never changes QVM ranks. Failures are recorded, not fatal.
    """
    out: dict[str, Any] = {"market": market}
    _job_phase(root, "정성 · 공식 RSS(킬스위치)", progress=0.56)
    try:
        from alpha_system.ui.services.killswitch_watch import refresh_killswitch_watch

        watch = refresh_killswitch_watch(root)
        out["killswitch_watch"] = {
            "hit_n": len(watch.hits),
            "feeds_ok": sum(1 for f in watch.feeds if f.get("ok")),
            "fetched_at": watch.fetched_at,
        }
    except Exception as exc:  # noqa: BLE001
        out["killswitch_watch_error"] = str(exc)[:200]

    _job_phase(root, "정성 · OpenDART 증분", progress=0.62)
    od = ensure_opendart_incremental_if_stale(
        root, market=market, force=True
    )
    out["opendart_pool_n"] = int(od.get("pool_n") or 0)
    if od.get("status") == "skipped":
        out["opendart_skipped"] = od.get("reason") or "no_watch_tickers"
    elif od.get("status") == "error":
        out["opendart_watch_error"] = od.get("error") or "error"
    else:
        out["opendart_watch"] = {
            "fetched_at": od.get("fetched_at") or "",
            "ticker_n": od.get("ticker_n") or od.get("pool_n") or 0,
            "missing_key": bool(od.get("missing_key")),
            "status": od.get("status"),
        }

    # 심층·PH-CVS 정밀 — 일상 확인①에 묶음 (포트 단독 버튼 대체)
    _job_phase(root, "정성 · 심층·PH-CVS 정밀", progress=0.70)
    review = refresh_review_boards_after_quant(root, market=market)
    out["review_boards"] = review

    # 형제 수급 브리핑 — Review-only · 점수·target 불변 · 실패 비치명
    _job_phase(root, "정성 · 형제 수급 브리핑", progress=0.78)
    try:
        from alpha_system.ui.services.pension_briefing_refresh import (
            refresh_pension_briefing,
        )

        pension = refresh_pension_briefing(root)
        out["pension_briefing"] = {
            "status": pension.get("status"),
            "asof": pension.get("asof") or "",
            "message": (pension.get("message") or "")[:200],
        }
    except Exception as exc:  # noqa: BLE001
        out["pension_briefing_error"] = str(exc)[:200]
    return out


def refresh_review_boards_after_quant(
    root: Path,
    *,
    market: str,
) -> dict[str, Any]:
    """심층 verify + PH-CVS stage1/정밀 · DART 추가 호출 없음(캐시 기준).

    Never writes target · never changes QVM ranks. Failures non-fatal.
    """
    from alpha_system.screen_book import source_data_dir

    mkt = normalize_market(market) or "KOSPI"
    data_dir = source_data_dir(root, mkt)
    tickers = _watch_pool_tickers(root, market=mkt, top_n=30)
    out: dict[str, Any] = {"market": mkt, "pool_n": len(tickers)}

    try:
        from alpha_system.review.screen_deep_verify import (
            build_screen_verify,
            save_screen_verify,
        )
        from alpha_system.ui.services.cecs_opendart_pack import load_opendart_watch

        snap = load_opendart_watch(root, data_dir=data_dir)
        watch_payload: dict[str, Any] = {}
        if snap is not None:
            watch_payload = {
                "evidence": list(getattr(snap, "evidence", None) or []),
                "flags": list(getattr(snap, "flags", None) or []),
                "metrics": list(getattr(snap, "metrics", None) or []),
            }
        board = build_screen_verify(
            root,
            data_dir=data_dir,
            tickers=tickers,
            opendart_watch=watch_payload or None,
            as_of=str(getattr(snap, "as_of", "") or "") if snap else "",
        )
        path = save_screen_verify(data_dir, board)
        out["screen_deep"] = {
            "ok": True,
            "path": str(path),
            "n": len(board.rows),
        }
    except Exception as exc:  # noqa: BLE001
        out["screen_deep"] = {"ok": False, "error": str(exc)[:240]}

    try:
        from alpha_system.review.phcvs_auto_eval import run_and_write as run_phcvs_stage1
        from alpha_system.review.phcvs_precision_eval import (
            run_and_write as run_phcvs_precision,
        )

        w, s = run_phcvs_stage1(root)
        p = run_phcvs_precision(root)
        out["phcvs"] = {
            "ok": True,
            "watch": str(w),
            "snapshot": str(s),
            "precision": str(p),
        }
    except Exception as exc:  # noqa: BLE001
        out["phcvs"] = {"ok": False, "error": str(exc)[:240]}
    return out


def persist_l3_review_after_shadow(
    root: Path,
    *,
    market: str,
) -> dict[str, Any]:
    """Shadow 재계산 후 L3·Fear Soft 디스크 저장 · Review-only."""
    mkt = (normalize_market(market) or "KOSPI").upper()
    local = Path(root) / "data" / "local"
    out: dict[str, Any] = {"market": mkt, "writes_target": False}
    try:
        from alpha_system.shadow.l3_crash_backtest import (
            run_l3_crash_backtest,
            save_report,
        )

        report = run_l3_crash_backtest(
            root, market=mkt, include_target=True
        )
        path = save_report(
            report, local / f"l3_crash_review_{mkt}.json"
        )
        out["l3"] = {
            "ok": True,
            "path": str(path),
            "events": int(report.event_count),
        }
    except Exception as exc:  # noqa: BLE001
        out["l3"] = {"ok": False, "error": str(exc)[:240]}
    try:
        from alpha_system.shadow.fear_soft_rebal_backtest import (
            run_fear_soft_rebal_backtest,
            save_fear_soft_report,
        )

        fear = run_fear_soft_rebal_backtest(root)
        fpath = save_fear_soft_report(
            fear, local / "fear_soft_review.json"
        )
        out["fear_soft"] = {"ok": True, "path": str(fpath)}
    except Exception as exc:  # noqa: BLE001
        out["fear_soft"] = {"ok": False, "error": str(exc)[:240]}
    return out


def _tail_lines(text: str, n: int = 40) -> str:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) <= n:
        return "\n".join(lines)
    return "\n".join(lines[-n:])


def _regime_snapshot(root: Path) -> dict[str, Any]:
    """Best-effort read of Tier-1 / regime sync state after analysis."""
    out: dict[str, Any] = {}
    mi_path = root / "data" / "market_indicators.csv"
    if mi_path.exists():
        try:
            import pandas as pd

            df = pd.read_csv(mi_path, dtype=str, keep_default_na=False)
            if not df.empty:
                row = df.iloc[-1]
                out["market_as_of"] = str(row.get("date") or "")
                out["regime"] = str(row.get("regime") or "")
                out["regime_expires"] = str(row.get("regime_expires_date") or "")
        except Exception as exc:
            out["market_read_error"] = str(exc)
    suggestion = root / "outputs" / "regime_auto_suggestion.json"
    if suggestion.exists():
        try:
            import json

            doc = json.loads(suggestion.read_text(encoding="utf-8"))
            out["regime_synced"] = bool(doc.get("auto_synced"))
            out["computed_regime"] = doc.get("computed_regime")
            out["applied_regime"] = doc.get("applied_regime")
        except Exception as exc:
            out["regime_suggestion_error"] = str(exc)
    health_path = root / "outputs" / "system_health.json"
    if health_path.exists():
        try:
            import json

            health = json.loads(health_path.read_text(encoding="utf-8"))
            out["health_overall"] = health.get("overall")
            for check in health.get("checks") or []:
                if check.get("name") == "core_price_gate":
                    out["core_price_gate"] = check.get("status")
                    out["core_price_gate_message"] = check.get("message")
                    break
        except Exception as exc:
            out["health_read_error"] = str(exc)
    return out


def run_compass_analysis(
    root: Path,
    *,
    run_mode: str = "standard",
    no_backtest: bool = False,
    timeout_sec: int = 1800,
) -> RefreshResult:
    """Run launcher [3] Analysis (`python -m src.main`) without approving target writes.

    Always passes ``--refresh-market`` so Tier-1 ``market_indicators``, Tier-A
    prices, and regime auto-sync run before analysis (standard mode alone is
    cache-first and would leave as_of / core prices stale). Does **not** pass
    ``--approve-target`` so ``target_portfolio.csv`` stays human-only.
    """
    mode = (run_mode or "standard").strip().lower() or "standard"
    command = [
        sys.executable,
        "-m",
        "src.main",
        "--data-dir",
        str(root / "data"),
        "--output-dir",
        str(root / "outputs"),
        "--run-mode",
        mode,
        "--refresh-market",
    ]
    if no_backtest:
        command.append("--no-backtest")

    _job_phase(root, "나침반·레짐 · 시장지표·Tier-1 분석", progress=0.08)
    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return RefreshResult(
            ok=False,
            message=(
                f"나침반 분석이 {timeout_sec // 60}분 안에 끝나지 않았습니다. "
                "장중·KRX 지연 시 런처 [3]로 다시 시도하세요."
            ),
            detail={"error": str(exc), "command": command},
        )
    except OSError as exc:
        return RefreshResult(
            ok=False,
            message=f"나침반 분석 실행 실패: {exc}",
            detail={"error": str(exc)},
        )

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    detail: dict[str, Any] = {
        "command": " ".join(command),
        "returncode": completed.returncode,
        "stdout_tail": _tail_lines(stdout),
        "stderr_tail": _tail_lines(stderr),
        "target_portfolio_written": False,
        "approve_target": False,
    }
    for line in stdout.splitlines():
        low = line.lower()
        if "actual buy allowed" in low:
            detail["actual_buy_allowed"] = line.split(":", 1)[-1].strip()
        if "data gate" in low:
            detail["data_gate"] = line.split(":", 1)[-1].strip()
        if low.startswith("health:"):
            detail["health"] = line.split(":", 1)[-1].strip()
        if low.startswith("run mode:"):
            detail["run_mode_line"] = line.strip()

    snap = _regime_snapshot(root)
    detail.update(snap)

    gate = str(detail.get("data_gate") or "").upper()
    regime_ok = bool(snap.get("market_as_of")) and (
        snap.get("regime_synced") is True
        or str(snap.get("regime") or "").upper() not in {"", "NEUTRAL", "AUTO"}
    )

    if completed.returncode != 0:
        # Regime Tier-1 may have refreshed even when full pipeline exits 1 on RED.
        if regime_ok and gate == "RED":
            price_msg = snap.get("core_price_gate_message") or "core ETF 시세 stale"
            bits = [
                f"레짐·Tier-1 갱신됨 (as_of {snap.get('market_as_of')}",
                f"레짐 {snap.get('applied_regime') or snap.get('regime')})",
                f"Data Gate RED — 실행 차단 ({price_msg})",
                "홈「정량 전체 갱신」또는 설정「시장지표 갱신」후 재실행",
            ]
            return RefreshResult(ok=True, message=" · ".join(bits), detail=detail)
        hint = (
            snap.get("core_price_gate_message")
            or detail.get("data_gate")
            or detail.get("stderr_tail")
            or detail.get("stdout_tail")
        )
        return RefreshResult(
            ok=False,
            message=f"나침반 분석 실패 (exit {completed.returncode})"
            + (f" · {hint}" if hint else ""),
            detail=detail,
        )

    bits = ["나침반·레짐 분석 완료"]
    if snap.get("market_as_of"):
        bits.append(f"as_of {snap['market_as_of']}")
    if detail.get("data_gate"):
        bits.append(f"Data Gate {detail['data_gate']}")
    if detail.get("actual_buy_allowed") is not None:
        bits.append(f"Actual Buy {detail['actual_buy_allowed']}")
    return RefreshResult(ok=True, message=" · ".join(bits), detail=detail)
