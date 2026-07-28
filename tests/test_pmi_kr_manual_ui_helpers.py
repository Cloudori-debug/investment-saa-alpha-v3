from __future__ import annotations

from pathlib import Path

from src.data_refresh.kosis_tier2_manual import save_pmi_kr_manual_fields, validate_pmi_kr_manual_ready
from src.data_refresh.price_store import atomic_write_text, inspect_text_bytes


def test_save_pmi_kr_manual_verified_true(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    save_pmi_kr_manual_fields(
        data,
        verified=True,
        value=52.1,
        value_date="2026-06-30",
        source="S&P Global PMI",
        source_url_or_note="https://example.com",
        updated_by="test_operator",
        update_reason="unit test",
    )
    ready = validate_pmi_kr_manual_ready(data)
    assert ready["verified"] is True
    assert ready["ready"] is True


def test_atomic_write_text_preserves_on_failure(tmp_path: Path) -> None:
    path = tmp_path / "tier2_kosis_manual.yaml"
    original = "fields:\n  pmi_kr:\n    verified: false\n"
    path.write_text(original, encoding="utf-8")
    try:
        atomic_write_text(path, "broken", min_bytes=10, verify=lambda _p: (_ for _ in ()).throw(RuntimeError("bad")))
    except RuntimeError:
        pass
    assert path.read_text(encoding="utf-8") == original
    assert inspect_text_bytes(path)["ok"] is True
