"""CECS facts from official OpenDART JSON — not DART/KIND HTML viewers.

Claude/web-search agents get 403/robots on dsaf001, report/viewer.do, KIND.
majorstock.json + list.json already carry holding % and payout titles.
"""

from __future__ import annotations

import re
import json
import sys
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[3]


@contextmanager
def _repo_src_on_top() -> Iterator[None]:
    """Prefer repo `src.data_refresh` over `alpha_portfolio/src`.

    Quant snapshot inserts alpha_portfolio first, so a plain
    `from src.data_refresh...` looks in the wrong package.
    """
    repo_s = str(_REPO_ROOT)
    src_mod = sys.modules.get("src")
    src_file = str(getattr(src_mod, "__file__", "") or "").replace("\\", "/")
    wrong_pkg = src_mod is not None and "/alpha_portfolio/" in f"/{src_file}"
    if not wrong_pkg:
        inserted = sys.path[:1] != [repo_s]
        if inserted:
            sys.path.insert(0, repo_s)
        try:
            yield
        finally:
            if inserted and sys.path[:1] == [repo_s]:
                sys.path.pop(0)
        return
    inserted = True
    sys.path.insert(0, repo_s)
    popped = {
        key: sys.modules.pop(key)
        for key in list(sys.modules)
        if key == "src" or key.startswith("src.")
    }
    try:
        yield
    finally:
        sys.modules.update(popped)
        if sys.path[:1] == [repo_s]:
            sys.path.pop(0)



_NPS_MARKERS = ("국민연금", "국민연금공단", "nps")
_PAYOUT_DIV = ("현금배당", "배당결정", "중간배당", "분기배당", "결산배당")
_PAYOUT_BUYBACK = ("자기주식취득", "자기주식 취득", "자사주 매입", "자사주매입")
_PAYOUT_CANCEL = ("자기주식소각", "자기주식 소각", "이익소각", "자사주소각")
_PURPOSE_CONTROL = ("경영참여", "경영권", "지배목적", "경영권 영향")
_PURPOSE_PASSIVE = ("단순투자", "일반투자")


DartGet = Callable[[str, dict[str, Any]], dict[str, Any]]

WATCH_FILENAME = "opendart_proposal_watch.json"
STALE_HOURS = 24 * 7


@dataclass(frozen=True)
class QualDraftFlag:
    ticker: str
    kind: str
    note: str
    source_url: str


@dataclass(frozen=True)
class CecsOpendartPack:
    markdown_by_ticker: dict[str, tuple[str, ...]]
    ok_count: int
    missing_key: bool
    notes: tuple[str, ...] = ()
    flags: tuple[QualDraftFlag, ...] = ()


@dataclass
class _TickerFacts:
    ticker: str
    corp_code: str = ""
    error: str = ""
    payout_events: list[dict[str, str]] = field(default_factory=list)
    quarters_hit: int | None = None
    nps_rows: list[dict[str, str]] = field(default_factory=list)
    latest_major: dict[str, str] | None = None


def last_four_completed_quarters(as_of: date) -> list[tuple[int, int]]:
    """Most recent four fully completed calendar quarters before as_of."""
    q = (as_of.month - 1) // 3 + 1
    year = as_of.year
    q -= 1
    if q == 0:
        q = 4
        year -= 1
    out: list[tuple[int, int]] = []
    for _ in range(4):
        out.append((year, q))
        q -= 1
        if q == 0:
            q = 4
            year -= 1
    out.reverse()
    return out


def quarter_of(day: date) -> tuple[int, int]:
    return day.year, (day.month - 1) // 3 + 1


def parse_ratio(raw: Any) -> float | None:
    text = str(raw or "").strip().replace(",", "").replace("%", "")
    if not text or text in {".", "-"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_yyyymmdd(raw: Any) -> date | None:
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) < 8:
        return None
    try:
        return datetime.strptime(digits[:8], "%Y%m%d").date()
    except ValueError:
        return None


def is_payout_title(title: str) -> str | None:
    """Return 'div' | 'buyback' | 'cancel' if the disclosure title is a payout event."""
    name = title or ""
    if any(k in name for k in _PAYOUT_CANCEL):
        return "cancel"
    if any(k in name for k in _PAYOUT_BUYBACK):
        return "buyback"
    if any(k in name for k in _PAYOUT_DIV):
        return "div"
    return None


def is_nps_reporter(name: str) -> bool:
    blob = (name or "").lower()
    return any(m.lower() in blob for m in _NPS_MARKERS)


def execution_hint(quarters_hit: int | None) -> str:
    if quarters_hit is None:
        return "환원 공시 미수집 → 점수 _____"
    n = max(0, min(4, int(quarters_hit)))
    return f"완결 4분기 중 충족 {n}/4 → 초안 {n * 25}"


def pension_hint(nps_rows: Sequence[dict[str, str]]) -> str:
    if not nps_rows:
        return "국민연금 5% 보고 없음(미보유 미확인) → 점수 _____ (추정 금지)"
    ratios: list[float] = []
    for row in nps_rows:
        val = parse_ratio(row.get("stkrt") if hasattr(row, "get") else None)
        if val is not None:
            ratios.append(val)
    if len(ratios) < 2:
        latest = ratios[0] if ratios else None
        if latest is None:
            return "국민연금 보고 1건·비율 없음 → 점수 _____"
        return f"국민연금 {latest:.2f}% 1건만(추세 불명) → 점수 _____ 또는 보수 50"
    delta = ratios[0] - ratios[-1]
    if abs(delta) <= 0.1:
        return f"국민연금 {ratios[-1]:.2f}%→{ratios[0]:.2f}% 보합 → 초안 50"
    if delta > 0:
        return f"국민연금 {ratios[-1]:.2f}%→{ratios[0]:.2f}% 순증 → 초안 70~100"
    return f"국민연금 {ratios[-1]:.2f}%→{ratios[0]:.2f}% 감소 → 초안 20~40"


def purpose_hint(
    report_tp: str,
    report_resn: str,
    *,
    as_of_year: int | None = None,
    filing_year: int | None = None,
) -> str:
    blob = f"{report_tp} {report_resn}"
    if filing_year is not None and as_of_year is not None and filing_year <= as_of_year - 3:
        return f"{filing_year}년 보고만(재확인 불가) → 점수 _____"
    if any(k in blob for k in _PURPOSE_CONTROL):
        return "경영참여/지배 문구 → 초안 30"
    if any(k in blob for k in _PURPOSE_PASSIVE):
        return "단순·일반투자 문구 → 초안 100"
    if not blob.strip():
        return "최신 대량보유 없음 → 초안 50(보고 없음)"
    return "약식/일반 형식만 있고 목적 문구 없음 → 점수 _____ (형식 추정 금지)"


def flags_from_facts(facts: _TickerFacts) -> list[QualDraftFlag]:
    """Program draft gates — not scores. Human still confirms overlay."""
    if facts.error:
        return []
    ticker = str(facts.ticker).zfill(6) if str(facts.ticker).isdigit() else str(facts.ticker)
    source = "https://opendart.fss.or.kr/"
    latest = facts.latest_major or {}
    rcept = re.sub(r"\D", "", str(latest.get("rcept_no") or ""))
    if rcept:
        source = f"https://opendart.fss.or.kr/#rcpNo={rcept}"
    out: list[QualDraftFlag] = []
    blob = f"{latest.get('report_tp') or ''} {latest.get('report_resn') or ''}"
    if any(k in blob for k in _PURPOSE_CONTROL):
        out.append(
            QualDraftFlag(
                ticker=ticker,
                kind="control_purpose",
                note=blob.strip()[:160],
                source_url=source,
            )
        )
    ratios: list[float] = []
    for row in facts.nps_rows:
        val = parse_ratio(row.get("stkrt"))
        if val is not None:
            ratios.append(val)
    if len(ratios) >= 2 and ratios[0] < ratios[-1] - 0.1:
        out.append(
            QualDraftFlag(
                ticker=ticker,
                kind="pension_exit",
                note=f"국민연금 {ratios[-1]:.2f}%→{ratios[0]:.2f}%",
                source_url=source,
            )
        )
    return out


MappingLike = Any


def format_facts_markdown(facts: _TickerFacts, *, as_of: date) -> tuple[str, ...]:
    lines = [
        "> **OpenDART 로컬 팩트** — HTML 뷰어·KIND를 열지 마세요. 이 숫자만으로 채점하세요.",
        f"> 수집 as_of `{as_of.isoformat()}` · API `list.json` + `majorstock.json`",
    ]
    if facts.error:
        lines.append(f"> 수집 실패: {facts.error}")
        lines.append("> 확인 불가 칸은 `_____` + 근거에 검색 키워드. 원문 추정 금지.")
        return tuple(lines)

    if facts.payout_events:
        bits = []
        for ev in facts.payout_events[:8]:
            bits.append(f"{ev.get('date') or '—'} {ev.get('kind') or ''} {ev.get('title') or ''}".strip())
        lines.append("> execution 공시: " + " · ".join(bits))
        lines.append(f"> execution 힌트: {execution_hint(facts.quarters_hit)}")
    else:
        lines.append("> execution 공시: 해당 기간 배당·자사주 취득/소각 제목 없음")
        lines.append(f"> execution 힌트: {execution_hint(facts.quarters_hit)}")

    if facts.nps_rows:
        nps_bits = []
        for row in facts.nps_rows[:6]:
            nps_bits.append(
                f"{row.get('date') or '—'} {row.get('stkrt') or '—'}%"
                f"(Δ{row.get('stkrt_irds') or '—'}) {row.get('report_tp') or ''}".strip()
            )
        lines.append("> pension 국민연금: " + " · ".join(nps_bits))
    else:
        lines.append("> pension 국민연금: 대량보유 JSON에 보고자 없음")
    lines.append(f"> pension 힌트: {pension_hint(facts.nps_rows)}")

    latest = facts.latest_major
    if latest:
        filing = parse_yyyymmdd(latest.get("date"))
        lines.append(
            "> purpose 최신 대량보유: "
            f"{latest.get('date') or '—'} {latest.get('repror') or '—'} "
            f"구분 `{latest.get('report_tp') or '—'}` "
            f"사유 `{latest.get('report_resn') or '—'}` "
            f"비율 `{latest.get('stkrt') or '—'}%`"
        )
        lines.append(
            "> purpose 힌트: "
            + purpose_hint(
                str(latest.get("report_tp") or ""),
                str(latest.get("report_resn") or ""),
                as_of_year=as_of.year,
                filing_year=filing.year if filing else None,
            )
        )
        rcept = re.sub(r"\D", "", str(latest.get("rcept_no") or ""))
        if rcept:
            lines.append(
                f"> 사람 확인용 링크(봇 수집 금지): https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept}"
            )
    else:
        lines.append("> purpose 최신 대량보유: 없음")
        lines.append("> purpose 힌트: " + purpose_hint("", "", as_of_year=as_of.year))
    lines.append("> 출처 칸에는 위 rcpNo 링크 또는 `https://opendart.fss.or.kr/` 를 적어도 됩니다.")
    return tuple(lines)


def collect_cecs_opendart_pack(
    root: Path,
    tickers: Sequence[str],
    *,
    as_of: date | None = None,
    dart_get_fn: DartGet | None = None,
    corp_map: dict[str, str] | None = None,
    include_payout: bool = True,
) -> CecsOpendartPack:
    """Fetch JSON facts. Never scrapes HTML viewers.

    include_payout=False skips list.json (배당·자사주) and only reads majorstock
    for proposal exclusion drafts.
    """
    as_of = as_of or date.today()
    data_dir = Path(root) / "data"
    notes: list[str] = []
    missing_key = False
    live_api = dart_get_fn is None
    limiter = None
    if live_api or corp_map is None:
        with _repo_src_on_top():
            from src.data_refresh.dart_client import (
                DartCredentialsError,
                RateLimiter,
                dart_get,
                get_dart_api_key,
            )
            from src.data_refresh.dart_corp_codes import build_ticker_corp_map

            if dart_get_fn is None:
                try:
                    get_dart_api_key(data_dir)
                except DartCredentialsError:
                    missing_key = True
                    md = {
                        str(t).zfill(6): _missing_key_lines(as_of)
                        for t in tickers
                        if str(t).strip()
                    }
                    return CecsOpendartPack(
                        markdown_by_ticker=md,
                        ok_count=0,
                        missing_key=True,
                        notes=("Open DART API 키 없음",),
                        flags=(),
                    )
                dart_get_fn = dart_get
            if corp_map is None:
                try:
                    corp_map = build_ticker_corp_map(data_dir, [str(t) for t in tickers])
                except Exception as exc:
                    notes.append(f"corp_code 표 실패: {exc}")
                    corp_map = {}
            limiter = RateLimiter(0.12) if live_api else None
    quarters = last_four_completed_quarters(as_of)
    lookback_start = date(quarters[0][0], (quarters[0][1] - 1) * 3 + 1, 1)
    bgn = lookback_start.strftime("%Y%m%d")
    end = as_of.strftime("%Y%m%d")

    markdown_by_ticker: dict[str, tuple[str, ...]] = {}
    flags: list[QualDraftFlag] = []
    ok = 0
    for raw in tickers:
        ticker = str(raw).strip()
        if ticker.isdigit():
            ticker = ticker.zfill(6)
        if not ticker:
            continue
        facts = _TickerFacts(ticker=ticker, corp_code=str((corp_map or {}).get(ticker) or ""))
        if not facts.corp_code:
            facts.error = "corp_code 없음"
            markdown_by_ticker[ticker] = format_facts_markdown(facts, as_of=as_of)
            continue
        try:
            if include_payout:
                if limiter:
                    limiter.wait()
                facts.payout_events, facts.quarters_hit = _payout_from_list(
                    dart_get_fn, facts.corp_code, bgn, end, quarters
                )
            if limiter:
                limiter.wait()
            facts.nps_rows, facts.latest_major = _majorstock_rows(
                dart_get_fn, facts.corp_code, lookback_start, as_of
            )
            ok += 1
        except Exception as exc:
            facts.error = str(exc)[:160]
            notes.append(f"{ticker}: {facts.error}")
        markdown_by_ticker[ticker] = format_facts_markdown(facts, as_of=as_of)
        flags.extend(flags_from_facts(facts))

    return CecsOpendartPack(
        markdown_by_ticker=markdown_by_ticker,
        ok_count=ok,
        missing_key=missing_key,
        notes=tuple(notes),
        flags=tuple(flags),
    )


def _missing_key_lines(as_of: date) -> tuple[str, ...]:
    return (
        "> **OpenDART 키 없음** — 설정에서 Open DART 인증키를 넣으면 대량보유·환원 공시가 붙습니다.",
        f"> as_of `{as_of.isoformat()}`. DART/KIND HTML 뷰어(dsaf001, viewer.do)는 봇 차단됩니다.",
        "> 웹검색으로 원문 지분율·보유목적을 추정하지 마세요. 점수 `_____` + 근거 `확인 불가`.",
    )


def _payout_from_list(
    dart_get_fn: DartGet,
    corp_code: str,
    bgn: str,
    end: str,
    quarters: Sequence[tuple[int, int]],
) -> tuple[list[dict[str, str]], int]:
    events: list[dict[str, str]] = []
    hit: set[tuple[int, int]] = set()
    want = set(quarters)
    for page in range(1, 4):
        data = dart_get_fn(
            "list.json",
            {
                "corp_code": corp_code,
                "bgn_de": bgn,
                "end_de": end,
                "page_no": page,
                "page_count": 100,
            },
        )
        items = data.get("list") or []
        if not items:
            break
        for item in items:
            title = str(item.get("report_nm") or "")
            kind = is_payout_title(title)
            if not kind:
                continue
            day = parse_yyyymmdd(item.get("rcept_dt"))
            if day is None:
                continue
            q = quarter_of(day)
            if q in want:
                hit.add(q)
            events.append(
                {
                    "date": day.isoformat(),
                    "kind": kind,
                    "title": re.sub(r"\s+", " ", title)[:80],
                    "rcept_no": str(item.get("rcept_no") or ""),
                }
            )
        if len(items) < 100:
            break
    events.sort(key=lambda r: r.get("date") or "", reverse=True)
    return events[:12], len(hit)


def _majorstock_rows(
    dart_get_fn: DartGet,
    corp_code: str,
    lookback_start: date,
    as_of: date,
) -> tuple[list[dict[str, str]], dict[str, str] | None]:
    data = dart_get_fn("majorstock.json", {"corp_code": corp_code})
    rows: list[dict[str, str]] = []
    for item in data.get("list") or []:
        day = parse_yyyymmdd(item.get("rcept_dt"))
        if day is None or day < lookback_start or day > as_of:
            continue
        rows.append(
            {
                "date": day.isoformat(),
                "repror": str(item.get("repror") or ""),
                "stkrt": str(item.get("stkrt") or ""),
                "stkrt_irds": str(item.get("stkrt_irds") or ""),
                "report_tp": str(item.get("report_tp") or ""),
                "report_resn": str(item.get("report_resn") or ""),
                "rcept_no": str(item.get("rcept_no") or ""),
            }
        )
    rows.sort(key=lambda r: r.get("date") or "", reverse=True)
    nps = [r for r in rows if is_nps_reporter(r.get("repror") or "")]
    latest = rows[0] if rows else None
    return nps[:8], latest


PAYOUT_SR4_CACHE = "opendart_payout_sr4.json"


def payout_sr4_window_key(as_of: date) -> str:
    return "|".join(f"{y}Q{q}" for y, q in last_four_completed_quarters(as_of))


def payout_sr4_cache_path(root: Path, *, market: str = "KOSPI") -> Path:
    from alpha_system.screen_book import normalize_market, operational_data_dir

    return operational_data_dir(Path(root), normalize_market(market)) / PAYOUT_SR4_CACHE


def collect_payout_sr4(
    root: Path,
    tickers: Sequence[str],
    *,
    as_of: date | None = None,
    dart_get_fn: DartGet | None = None,
    cache_path: Path | None = None,
    market: str = "KOSPI",
    corp_map: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """OpenDART list.json → 완결 4분기 환원 공시 칸 수. CECS 순위에 안 넣음.

    Fail-open when the API key is missing. Reuses cache for the same quarter window.
    """
    as_of = as_of or date.today()
    wanted = _norm_tickers(tickers)
    if not wanted:
        return {}
    window = payout_sr4_window_key(as_of)
    path = cache_path or payout_sr4_cache_path(root, market=market)
    cached = _load_payout_sr4_cache(path, window=window)
    missing = [t for t in wanted if t not in cached]

    live_api = dart_get_fn is None
    if missing:
        with _repo_src_on_top():
            from src.data_refresh.dart_client import (
                DartCredentialsError,
                RateLimiter,
                dart_get,
                get_dart_api_key,
            )
            from src.data_refresh.dart_corp_codes import build_ticker_corp_map

            if dart_get_fn is None:
                data_dir = Path(root) / "data"
                try:
                    get_dart_api_key(data_dir)
                except DartCredentialsError:
                    return {k: dict(v) for k, v in cached.items() if k in set(wanted)}
                dart_get_fn = dart_get
            if corp_map is None:
                try:
                    corp_map = build_ticker_corp_map(Path(root) / "data", missing)
                except Exception:
                    corp_map = {}
            limiter = RateLimiter(0.12) if live_api else None
            quarters = last_four_completed_quarters(as_of)
            lookback_start = date(quarters[0][0], (quarters[0][1] - 1) * 3 + 1, 1)
            bgn = lookback_start.strftime("%Y%m%d")
            end = as_of.strftime("%Y%m%d")
            for ticker in missing:
                corp = str((corp_map or {}).get(ticker) or "")
                if not corp:
                    continue
                try:
                    if limiter:
                        limiter.wait()
                    events, hit = _payout_from_list(dart_get_fn, corp, bgn, end, quarters)
                except Exception:
                    continue
                cached[ticker] = {
                    "quarters_hit": int(hit),
                    "buyback_3y": any(e.get("kind") in {"buyback", "cancel"} for e in events),
                }
        _save_payout_sr4_cache(path, window=window, as_of=as_of, rows=cached)

    return {k: dict(cached[k]) for k in wanted if k in cached}


def apply_payout_sr4(frame: Any, rows: dict[str, dict[str, Any]]) -> Any:
    """Write execution_quarters_hit / buyback_3y onto a screening frame."""
    import pandas as pd

    if frame is None or getattr(frame, "empty", True) or not rows:
        return frame
    out = frame.copy()
    if "ticker" not in out.columns:
        return out
    if "execution_quarters_hit" not in out.columns:
        out["execution_quarters_hit"] = pd.NA
    if "buyback_3y" not in out.columns:
        out["buyback_3y"] = pd.NA
    tickers = out["ticker"].astype(str).map(lambda t: t.zfill(6) if str(t).isdigit() else str(t))
    for idx, ticker in tickers.items():
        info = rows.get(ticker)
        if not info:
            continue
        hit = info.get("quarters_hit")
        if hit is not None:
            out.at[idx, "execution_quarters_hit"] = int(hit)
        if "buyback_3y" in info:
            out.at[idx, "buyback_3y"] = bool(info["buyback_3y"])
    return out


def _load_payout_sr4_cache(path: Path, *, window: str) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(data, dict) or str(data.get("window") or "") != window:
        return {}
    rows = data.get("rows")
    if not isinstance(rows, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for raw_tk, raw_row in rows.items():
        if not isinstance(raw_row, dict):
            continue
        tk = str(raw_tk).zfill(6) if str(raw_tk).isdigit() else str(raw_tk)
        hit = raw_row.get("quarters_hit")
        try:
            n = int(hit)
        except (TypeError, ValueError):
            continue
        out[tk] = {
            "quarters_hit": n,
            "buyback_3y": bool(raw_row.get("buyback_3y")),
        }
    return out


def _save_payout_sr4_cache(
    path: Path,
    *,
    window: str,
    as_of: date,
    rows: dict[str, dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "window": window,
        "as_of": as_of.isoformat(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "rows": {
            tk: {
                "quarters_hit": int(row["quarters_hit"]),
                "buyback_3y": bool(row.get("buyback_3y")),
            }
            for tk, row in rows.items()
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _norm_tickers(tickers: Sequence[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in tickers:
        text = str(raw or "").strip()
        if text.isdigit():
            text = text.zfill(6)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


@dataclass
class OpendartProposalWatch:
    version: int = 1
    fetched_at: str = ""
    as_of: str = ""
    tickers: list[str] = field(default_factory=list)
    missing_key: bool = False
    notes: list[str] = field(default_factory=list)
    flags: list[dict[str, str]] = field(default_factory=list)

    def flag_models(self) -> tuple[QualDraftFlag, ...]:
        out: list[QualDraftFlag] = []
        for raw in self.flags:
            try:
                out.append(
                    QualDraftFlag(
                        ticker=str(raw.get("ticker") or ""),
                        kind=str(raw.get("kind") or ""),
                        note=str(raw.get("note") or ""),
                        source_url=str(raw.get("source_url") or ""),
                    )
                )
            except (TypeError, ValueError):
                continue
        return tuple(f for f in out if f.ticker and f.kind)


def opendart_watch_path(root: Path) -> Path:
    return Path(root) / "data" / WATCH_FILENAME


def load_opendart_watch(root: Path) -> OpendartProposalWatch | None:
    path = opendart_watch_path(root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return OpendartProposalWatch(
        version=int(data.get("version") or 1),
        fetched_at=str(data.get("fetched_at") or ""),
        as_of=str(data.get("as_of") or ""),
        tickers=list(data.get("tickers") or []),
        missing_key=bool(data.get("missing_key")),
        notes=list(data.get("notes") or []),
        flags=list(data.get("flags") or []),
    )


def _parse_iso(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def watch_needs_refresh(
    snap: OpendartProposalWatch | None,
    tickers: Sequence[str],
    *,
    hours: int = STALE_HOURS,
) -> bool:
    wanted = _norm_tickers(tickers)
    if not wanted:
        return False
    if snap is None or not snap.fetched_at:
        return True
    if set(_norm_tickers(snap.tickers)) != set(wanted):
        return True
    if snap.missing_key:
        return False
    fetched = _parse_iso(snap.fetched_at)
    if fetched is None:
        return True
    now = datetime.now(timezone.utc)
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return now - fetched > timedelta(hours=hours)


def refresh_opendart_proposal_watch(
    root: Path,
    tickers: Sequence[str],
    *,
    as_of: date | None = None,
    dart_get_fn: DartGet | None = None,
    corp_map: dict[str, str] | None = None,
    journal_path: Path | None = None,
) -> OpendartProposalWatch:
    """Search confirmed proposal names only. Never writes overlay or target_portfolio."""
    from alpha_system.journal import append_record

    day = as_of or date.today()
    wanted = _norm_tickers(tickers)
    pack = collect_cecs_opendart_pack(
        root,
        wanted,
        as_of=day,
        dart_get_fn=dart_get_fn,
        corp_map=corp_map,
        include_payout=False,
    )
    snap = OpendartProposalWatch(
        version=1,
        fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        as_of=day.isoformat(),
        tickers=wanted,
        missing_key=pack.missing_key,
        notes=list(pack.notes[:8]),
        flags=[
            {
                "ticker": f.ticker,
                "kind": f.kind,
                "note": f.note,
                "source_url": f.source_url,
            }
            for f in pack.flags
        ],
    )
    path = opendart_watch_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(snap), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    append_record(
        action_kind="OPENDART_WATCH",
        as_of=day,
        subject="proposal",
        rationale=(
            f"제안 {len(wanted)}종 OpenDART 탐색 · 후보 {len(snap.flags)}건"
            + (" · API 키 없음" if pack.missing_key else "")
        ),
        payload={
            "path": str(path),
            "tickers": wanted,
            "flag_n": len(snap.flags),
            "missing_key": pack.missing_key,
        },
        journal_path=journal_path,
    )
    return snap

