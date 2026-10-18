import json
import sqlite3
from pathlib import Path

import pytest

from wardprice_webpilot import ui_service


def _targets_db(path):
    database = sqlite3.connect(path)
    database.execute(
        """CREATE TABLE ward_target_legacy(
            rank INTEGER PRIMARY KEY, old_ward TEXT, old_district TEXT, old_province TEXT
        )"""
    )
    for rank in range(1, 51):
        ward = "Phường Bình Trị Đông" if rank == 11 else f"Phường Test {rank}"
        database.execute(
            "INSERT INTO ward_target_legacy VALUES(?,?,?,?)",
            (rank, ward, "Quận Bình Tân", "Thành phố Hồ Chí Minh"),
        )
    database.commit()
    database.close()


def test_ui_live_request_caps_output_and_keeps_cookie_out_of_audit(tmp_path, monkeypatch):
    targets_db = tmp_path / "targets.sqlite3"
    audit_db = tmp_path / "audit.sqlite3"
    inbox = tmp_path / "inbox"
    _targets_db(targets_db)
    secrets = {"cookie": None, "token": None}
    listings = [
        {
            "target_rank": 11,
            "original_ward": "Phường Bình Trị Đông",
            "property_type": "NHA_RIENG",
            "title": f"Nhà riêng Bình Trị Đông {index}",
            "address": f"Phường Bình Trị Đông, Quận Bình Tân, Thành phố Hồ Chí Minh, số {index}",
            "price_vnd": 5_000_000_000 + index,
            "area_m2": 70 + index,
            "source_url": f"https://example.com/listing-{index}",
        }
        for index in range(12)
    ]

    async def fake_collect(prompt, model=None, *, session_cookie=None, session_token=None):
        secrets["cookie"] = session_cookie
        secrets["token"] = session_token
        assert "Phường Bình Trị Đông" in prompt
        return "session-secret-123\n" + json.dumps({"listings": listings}), []

    monkeypatch.setattr(ui_service.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr("wardprice_webpilot.webclient.collect_from_web", fake_collect)
    monkeypatch.delenv("GEMINI_SECURE_1PSID", raising=False)
    monkeypatch.delenv("GEMINI_SECURE_1PSIDTS", raising=False)

    result = ui_service.run_live_collection(
        targets_db=targets_db,
        audit_db=audit_db,
        inbox=inbox,
        rank=11,
        count=10,
        session_cookie="session-secret-123",
        session_token="session-token-secret",
    )

    assert secrets == {"cookie": "session-secret-123", "token": "session-token-secret"}
    assert result["status"] == "COMPLETE"
    assert result["response_listing_count"] == 12
    assert result["received"] == result["inserted_candidates"] == 10
    assert result["truncated_to_limit"] == 2
    assert result["source_verified_count"] == 0
    assert result["production_database_written"] is False
    assert "session-secret-123" not in json.dumps(result)
    assert "session-token-secret" not in json.dumps(result)
    assert "session-secret-123" not in Path(result["raw_response_file"]).read_text(
        encoding="utf-8"
    )

    audit = sqlite3.connect(audit_db)
    try:
        assert audit.execute("SELECT COUNT(*) FROM webpilot_candidates").fetchone()[0] == 10
        audit_dump = json.dumps(audit.execute("SELECT * FROM webpilot_runs").fetchall())
        assert "session-secret-123" not in audit_dump
        assert "session-token-secret" not in audit_dump
    finally:
        audit.close()

    target = sqlite3.connect(targets_db)
    try:
        assert target.execute("SELECT COUNT(*) FROM ward_target_legacy").fetchone()[0] == 50
        assert target.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='listings'"
        ).fetchone()[0] == 0
    finally:
        target.close()


def test_ui_service_rejects_more_than_ten_before_network(tmp_path, monkeypatch):
    targets_db = tmp_path / "targets.sqlite3"
    _targets_db(targets_db)

    def fail_if_called(*args, **kwargs):
        pytest.fail("network adapter should not run for a count above the UI cap")

    monkeypatch.setattr("wardprice_webpilot.webclient.collect_from_web", fail_if_called)
    with pytest.raises(ValueError, match="tối đa 10"):
        ui_service.run_live_collection(
            targets_db=targets_db,
            audit_db=tmp_path / "audit.sqlite3",
            inbox=tmp_path / "inbox",
            rank=11,
            count=11,
            session_cookie="test-cookie",
        )


def test_ui_candidates_are_read_from_sidecar_and_scoped_to_selected_rank(tmp_path):
    audit_db = tmp_path / "audit.sqlite3"
    database = ui_service.connect(audit_db)
    database.close()
    assert ui_service.recent_candidates(audit_db, 11) == []
