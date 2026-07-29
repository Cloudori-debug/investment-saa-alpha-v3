"""Basel III thematic timeline board — Review-only read UI.

Loads data/basel_theme_phases.yaml. Optional Ph4 anchor notes in
data/local/basel_ph4_anchor.json (gitignored via data/local/).

Does NOT change Core QVM, scores, or target_portfolio.csv.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

YAML_REL = Path("data") / "basel_theme_phases.yaml"
ANCHOR_REL = Path("data") / "local" / "basel_ph4_anchor.json"

THEME_KO: dict[str, str] = {
    "BX_SME_CREDIT": "중소·기업여신 여력 (은행·내수)",
    "BX_LARGE_BANK": "대형 은행지주·우량 대기업",
    "BX_LEX_LIMIT": "거액익스포저·분산 여신",
    "BX_BUFFER_CAP": "완충자본·CET1 두꺼운 지주",
    "BX_FLOOR_UP": "자본하한 상향 → 저RW·담보·우량 / 무등급 중소 부담",
    "BX_FLOOR_FINAL": "자본하한 최종(72.5%) · 저위험 선호 정점",
    "BX_PROD_FIN": "생산적 금융(발표 지정 산업만)",
}

STATUS_KO: dict[str, str] = {
    "historical": "기시행",
    "active": "진행",
    "active_soft": "진행(날짜 Soft)",
    "pending_ph4_anchor": "Ph4 앵커 대기",
    "target": "목표",
    "overlay": "병행·이벤트",
}

# Concrete Ph4 anchor checklist (operator Review notes).
PH4_CHECKLIST: tuple[tuple[str, str], ...] = (
    (
        "fss_fsc_notice",
        "금융위·금감원 보도/안내: 자본하한(output floor) 적용 비율 k%·적용 시점 명시",
    ),
    (
        "supervisory_rule",
        "은행업감독규정·시행세칙(또는 Q&A): 위험가중자산 하한 비율·시행일 조문 확인",
    ),
    (
        "bank_disclosure_k",
        "주요 은행·지주 사업보고서/실적자료: 「적용 자본하한 ○○%」 또는 동등 공시",
    ),
    (
        "bis_footnote",
        "BIS비율 산출 주석: IRB·표준방법·하한(k%) 중 무엇이 구속인지 확인",
    ),
    (
        "no_media_only",
        "언론 단독 수치만으로 T0를 찍지 않음(위 공식·공시 중 ≥1 확보)",
    ),
    (
        "s5_overlay_note",
        "같은 시기 「생산적 금융」위험가중 예외 발표 유무 메모(있으면 Ph7 병기)",
    ),
)


@dataclass(frozen=True)
class PhaseRow:
    id: str
    stage: str
    theme: str
    theme_ko: str
    status: str
    status_ko: str
    t0: date | None
    t0_label: str
    error_months: int
    early_from: date | None
    early_to: date | None
    window: str
    """선진입 창 상태: 열림 / 대기 / 종료 / Soft(앵커필요)"""
    note: str


@dataclass(frozen=True)
class Ph4AnchorState:
    checks: dict[str, bool]
    t0: date | None
    k_pct: float | None
    evidence_note: str
    anchored: bool
    """True if t0 set and minimum checklist satisfied."""


@dataclass(frozen=True)
class BaselThemeBoard:
    as_of: date
    yaml_updated: str
    rows: tuple[PhaseRow, ...]
    ph4: Ph4AnchorState
    summary: str
    active_themes: tuple[str, ...]


def _parse_date(raw: Any) -> date | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    s = str(raw).strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _add_months(d: date, months: int) -> date:
    y, m = d.year, d.month + months
    while m > 12:
        y += 1
        m -= 12
    while m < 1:
        y -= 1
        m += 12
    for day in (
        d.day,
        28,
        27,
        26,
        25,
        24,
        23,
        22,
        21,
        20,
        19,
        18,
        17,
        16,
        15,
        14,
        13,
        12,
        11,
        10,
        9,
        8,
        7,
        6,
        5,
        4,
        3,
        2,
        1,
    ):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    return date(y, m, 1)


def load_phases_yaml(root: Path) -> dict[str, Any]:
    path = root / YAML_REL
    if not path.exists():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return raw if isinstance(raw, dict) else {}


def load_ph4_anchor(root: Path) -> Ph4AnchorState:
    path = root / ANCHOR_REL
    checks = {k: False for k, _ in PH4_CHECKLIST}
    t0 = None
    k_pct = None
    note = ""
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            data = {}
        if isinstance(data, dict):
            raw_c = data.get("checks") or {}
            if isinstance(raw_c, dict):
                for k in checks:
                    checks[k] = bool(raw_c.get(k))
            t0 = _parse_date(data.get("t0"))
            try:
                if data.get("k_pct") is not None and str(data.get("k_pct")).strip() != "":
                    k_pct = float(data["k_pct"])
            except (TypeError, ValueError):
                k_pct = None
            note = str(data.get("evidence_note") or "")
    core_ok = checks.get("fss_fsc_notice") or checks.get("supervisory_rule") or checks.get(
        "bank_disclosure_k"
    )
    anchored = bool(t0) and bool(core_ok) and bool(checks.get("no_media_only"))
    return Ph4AnchorState(
        checks=checks,
        t0=t0,
        k_pct=k_pct,
        evidence_note=note,
        anchored=anchored,
    )


def save_ph4_anchor(
    root: Path,
    *,
    checks: dict[str, bool],
    t0: date | None,
    k_pct: float | None,
    evidence_note: str,
) -> Path:
    path = root / ANCHOR_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "checks": {k: bool(checks.get(k)) for k, _ in PH4_CHECKLIST},
        "t0": t0.isoformat() if t0 else None,
        "k_pct": k_pct,
        "evidence_note": evidence_note,
        "review_only": True,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _window_label(
    *,
    as_of: date,
    early_from: date | None,
    early_to: date | None,
    soft_need_anchor: bool,
) -> str:
    if soft_need_anchor:
        return "Soft · Ph4 앵커 필요"
    if early_from is None:
        return "—"
    if as_of < early_from:
        return "대기(선진입 전)"
    if early_to is not None and as_of > early_to:
        return "창 종료·재평가"
    return "선진입·관찰 열림"


def build_basel_theme_board(
    root: Path,
    *,
    as_of: date | None = None,
) -> BaselThemeBoard:
    as_of = as_of or date.today()
    cfg = load_phases_yaml(root)
    early_m = int((cfg.get("early_entry") or {}).get("months_before_t0") or 6)
    themes = cfg.get("themes") or {}
    phases = cfg.get("phases") or []
    ph4 = load_ph4_anchor(root)

    t0_by_id: dict[str, date | None] = {}
    for p in phases:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or "")
        t0_by_id[pid] = _parse_date(p.get("t0"))

    if ph4.anchored and ph4.t0 is not None:
        t0_by_id["Ph4"] = ph4.t0
        for p in phases:
            if not isinstance(p, dict):
                continue
            if str(p.get("id")) == "Ph5" and p.get("t0_offset_months_from") == "Ph4":
                off = int(p.get("t0_offset_months") or 12)
                t0_by_id["Ph5"] = _add_months(ph4.t0, off)

    rows: list[PhaseRow] = []
    active_themes: list[str] = []
    for p in phases:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or "")
        theme = str(p.get("theme") or "")
        status = str(p.get("status") or "")
        err = int(p.get("error_months") or 6)
        t0 = t0_by_id.get(pid)
        note = str(p.get("t0_note") or "")

        early_from = _parse_date(p.get("early_entry_from"))
        if early_from is None and t0 is not None:
            early_from = _add_months(t0, -early_m)
        early_to = _add_months(t0, err) if t0 is not None else None

        soft_need = pid == "Ph4" and not ph4.anchored
        if pid == "Ph5" and not ph4.anchored:
            soft_need = True

        win = _window_label(
            as_of=as_of,
            early_from=None if soft_need else early_from,
            early_to=None if soft_need else early_to,
            soft_need_anchor=soft_need,
        )
        if win == "선진입·관찰 열림" and theme:
            active_themes.append(theme)

        theme_meta = themes.get(theme) if isinstance(themes, dict) else None
        extra = ""
        if isinstance(theme_meta, dict) and theme_meta.get("note"):
            extra = str(theme_meta["note"])

        t0_label = t0.isoformat() if t0 else ("미앵커" if pid in {"Ph4", "Ph5", "Ph7"} else "—")
        rows.append(
            PhaseRow(
                id=pid,
                stage=str(p.get("stage") or ""),
                theme=theme,
                theme_ko=THEME_KO.get(theme, theme),
                status=status,
                status_ko=STATUS_KO.get(status, status),
                t0=t0,
                t0_label=t0_label,
                error_months=err,
                early_from=early_from if not soft_need else None,
                early_to=early_to if not soft_need else None,
                window=win,
                note=(note + (" · " + extra if extra else "")).strip(" ·"),
            )
        )

    open_n = sum(1 for r in rows if r.window == "선진입·관찰 열림")
    if ph4.anchored:
        ph4_txt = f"Ph4 앵커됨 T0={ph4.t0} k={ph4.k_pct if ph4.k_pct is not None else '—'}"
    else:
        ph4_txt = "Ph4 미앵커(공식·공시 체크 후 T0 입력)"
    summary = (
        f"바젤·건전성 테마 시계열 · {ph4_txt} · "
        f"선진입 창 열림 {open_n} · Review-only · Core·target 불변"
    )

    seen: set[str] = set()
    uniq: list[str] = []
    for t in active_themes:
        if t not in seen:
            seen.add(t)
            uniq.append(THEME_KO.get(t, t))

    return BaselThemeBoard(
        as_of=as_of,
        yaml_updated=str(cfg.get("updated") or ""),
        rows=tuple(rows),
        ph4=ph4,
        summary=summary,
        active_themes=tuple(uniq),
    )


def rows_as_table_dicts(board: BaselThemeBoard) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in board.rows:
        out.append(
            {
                "단계": r.id,
                "레버": r.stage,
                "상태": r.status_ko,
                "목표T0": r.t0_label,
                "오차(월)": r.error_months,
                "선진입시작": r.early_from.isoformat() if r.early_from else "—",
                "창": r.window,
                "수혜테마": r.theme_ko,
            }
        )
    return out


LOG_REL = Path("data") / "local" / "basel_theme_timeline_log.jsonl"


def _read_log(root: Path) -> list[dict[str, Any]]:
    path = root / LOG_REL
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return rows


def persist_basel_window_log(root: Path, board: BaselThemeBoard) -> None:
    """Append one line per as_of when open-window set or Ph4 anchor changes."""
    path = root / LOG_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    open_ids = sorted(r.id for r in board.rows if r.window == "선진입·관찰 열림")
    fingerprint = {
        "as_of": board.as_of.isoformat(),
        "open_ids": open_ids,
        "ph4_anchored": board.ph4.anchored,
        "ph4_t0": board.ph4.t0.isoformat() if board.ph4.t0 else None,
        "ph4_k": board.ph4.k_pct,
    }
    existing = _read_log(root)
    # Skip duplicate same-day same fingerprint
    for prev in reversed(existing[-20:]):
        if str(prev.get("as_of") or "")[:10] != fingerprint["as_of"]:
            continue
        if (
            prev.get("open_ids") == open_ids
            and bool(prev.get("ph4_anchored")) == board.ph4.anchored
            and prev.get("ph4_t0") == fingerprint["ph4_t0"]
            and prev.get("ph4_k") == fingerprint["ph4_k"]
        ):
            return
        break
    existing.append(
        {
            **fingerprint,
            "recorded_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "active_themes": list(board.active_themes),
            "review_only": True,
        }
    )
    if len(existing) > 2000:
        existing = existing[-2000:]
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in existing),
        encoding="utf-8",
    )


@dataclass(frozen=True)
class BaselAutoCue:
    """Review-only home/action cue — never writes target/Core."""

    key: str
    title: str
    detail: str
    severity: str  # info | warn
    phase_ids: tuple[str, ...] = ()


def build_basel_auto_cues(
    root: Path,
    *,
    as_of: date | None = None,
    persist_log: bool = True,
) -> tuple[BaselThemeBoard, tuple[BaselAutoCue, ...]]:
    """Automation that is safe: detect open windows / missing Ph4 anchor + log."""
    board = build_basel_theme_board(root, as_of=as_of)
    if persist_log:
        try:
            persist_basel_window_log(root, board)
        except OSError:
            pass

    cues: list[BaselAutoCue] = []
    if not board.ph4.anchored:
        cues.append(
            BaselAutoCue(
                key="basel_ph4_anchor",
                title="바젤 Ph4 날짜 미확정",
                detail=(
                    "자본하한(k%) 적용일을 공식·공시로 확인하세요. "
                    "홈/레짐「바젤·건전성 테마」에서 Ph4 앵커 체크. "
                    "자동매수·순위 변경 없음."
                ),
                severity="warn",
                phase_ids=("Ph4", "Ph5"),
            )
        )

    open_rows = [r for r in board.rows if r.window == "선진입·관찰 열림"]
    if open_rows:
        names = " · ".join(f"{r.id}:{r.theme_ko}" for r in open_rows[:4])
        more = f" 외 {len(open_rows) - 4}건" if len(open_rows) > 4 else ""
        cues.append(
            BaselAutoCue(
                key="basel_early_windows",
                title=f"바젤 테마 선진입·관찰 창 {len(open_rows)}건",
                detail=(
                    f"{names}{more}. T−6M 관찰만 · 워치·Review · "
                    "편입은 QVM·목표가·익절 규칙이 우선 · target 불변."
                ),
                severity="info",
                phase_ids=tuple(r.id for r in open_rows),
            )
        )

    # Ph6 approaching within 6M even if not yet "open" by early_from (belt)
    for r in board.rows:
        if r.id != "Ph6" or r.t0 is None:
            continue
        days = (r.t0 - board.as_of).days
        if 0 <= days <= 200 and r.window != "선진입·관찰 열림":
            cues.append(
                BaselAutoCue(
                    key="basel_ph6_approaching",
                    title="바젤 최종 하한(Ph6) 접근",
                    detail=(
                        f"목표 T0≈{r.t0.isoformat()} (D-{days}). "
                        "저위험·담보 선호 테마 관찰 준비 · Review-only."
                    ),
                    severity="info",
                    phase_ids=("Ph6",),
                )
            )

    return board, tuple(cues)
