"""Optional Streamlit smoke test; it exercises only the local dry-run action."""

import importlib.util
from pathlib import Path

import pytest

from wardprice.database import connect


def _run_counts(database):
    db = connect(database)
    try:
        return (
            db.execute("SELECT COUNT(*) FROM run_log").fetchone()[0],
            db.execute("SELECT COUNT(*) FROM listing_search_runs").fetchone()[0],
        )
    finally:
        db.close()


def test_dashboard_renders_and_dry_run_is_read_only(tmp_path, monkeypatch):
    if importlib.util.find_spec("streamlit") is None:
        pytest.skip("install the optional [ui] dependency to run the UI smoke test")
    from streamlit.testing.v1 import AppTest

    database = tmp_path / "state.sqlite3"
    monkeypatch.setenv("WARDPRICE_DB_PATH", str(database))
    monkeypatch.setenv("WARDPRICE_OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("WARDPRICE_ADMIN_VIEW", "1")
    before = _run_counts(database)
    db = connect(database)
    try:
        db.execute(
            """INSERT INTO ward_registry(
               ward_code,ward_name,province,district,admin_source,active,imported_at
               ) VALUES('T0001','Phường Kiểm Thử','Tỉnh Kiểm Thử','Quận Kiểm Thử',
               'pytest fixture',1,'2026-10-13T00:00:00+00:00')"""
        )
        db.commit()
    finally:
        db.close()
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "wardprice" / "ui.py")).run()
    assert not app.exception
    workspace = next(radio for radio in app.radio if radio.label == "Không gian")
    workspace.set_value("Quản trị").run()
    assert not app.exception
    assert any("Theo dõi thu thập dữ liệu web" in element.value for element in app.subheader)

    preview_button = next(button for button in app.button if button.label == "Xem trước các bước")
    preview_button.click().run()

    assert not app.exception
    assert any("network_request" in str(element.value) for element in app.json)
    assert _run_counts(database) == before
