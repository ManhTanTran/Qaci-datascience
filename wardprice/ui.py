"""Local Streamlit app with a public price lookup and a separate admin dashboard."""

from __future__ import annotations

import html
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from wardprice.config import PROJECT_ROOT, Settings
from wardprice.database import (
    active_wards,
    connect,
    listing_call_count,
    listing_rows,
    listing_statistics,
    tracked_listing_count,
)
from wardprice.demo import (
    DEMO_DB,
    FIXTURE_DIR,
    demo_coverage,
    demo_database,
    demo_history,
    demo_lookup,
    demo_wards,
    run_demo_scheduler,
)
from wardprice.listing_pipeline import preview_listing_selection, run_listing_cycle
from wardprice.mailer import dry_run_report
from wardprice.national_registry import (
    AREA_BASES,
    WardLookupService,
    WardPriceLookupService,
    national_collection_priorities,
    national_coverage,
    normalize_admin_name,
)
from wardprice.reports import export

DEFAULT_DB = Path(
    os.getenv("WARDPRICE_DB_PATH", str(PROJECT_ROOT / "state" / "ward_prices.sqlite3"))
)
DEFAULT_OUTPUT = Path(os.getenv("WARDPRICE_OUTPUT_DIR", str(PROJECT_ROOT / "outputs")))
WEBPILOT_AUDIT_DB = Path(
    os.getenv(
        "WARDPRICE_WEBPILOT_DB_PATH",
        str(PROJECT_ROOT / "state" / "wardprice_webpilot.sqlite3"),
    )
)
WEBPILOT_INBOX = PROJECT_ROOT / "inbox" / "webpilot"
INGESTION_PILOT_DB = Path(
    os.getenv(
        "WARDPRICE_INGESTION_PILOT_DB_PATH",
        str(PROJECT_ROOT / "state" / "ward_prices.ingestion_pilot.sqlite3"),
    )
)
PROPERTY_TYPES = ("DAT_O", "NHA_RIENG", "CHUNG_CU")


def _recent_activity(db):
    return [
        dict(row)
        for row in db.execute(
            """SELECT s.run_id,s.started_at,s.finished_at,w.ward_name,w.province,
                      s.status,s.accepted_count,s.updated_count,s.rejected_count,
                      s.search_queries,s.grounding_used,s.error
               FROM listing_search_runs s
               LEFT JOIN ward_registry w ON w.ward_code=s.ward_code
               ORDER BY s.started_at DESC,s.id DESC LIMIT 12"""
        ).fetchall()
    ]


def _snapshot(settings):
    db = connect(DEFAULT_DB)
    try:
        recent = _recent_activity(db)
        for row in recent:
            if row["error"] and settings.api_key:
                row["error"] = str(row["error"]).replace(settings.api_key, "[redacted]")
        return {
            "wards": active_wards(db),
            "listings": listing_rows(db),
            "statistics": listing_statistics(db),
            "tracked": tracked_listing_count(db),
            "calls_used": listing_call_count(db),
            "recent": recent,
            "selection": preview_listing_selection(db, settings),
        }
    finally:
        db.close()


def _redact_error(exc, api_key):
    message = str(exc)
    if api_key:
        message = message.replace(api_key, "[redacted]")
    return message[:1000] or type(exc).__name__


def _render_styles(st):
    st.markdown(
        """<style>
        :root { color-scheme: light; }
        :root {
          --canvas:#F2F4EF; --paper:#FFFEFA; --ink:#203431; --muted:#63736E;
          --line:#DCE4DB; --teal:#17665B; --pine:#123D35; --amber:#D5A34E;
          --source:#5D7E78; --rust:#A94F3D;
        }
        .stApp { background:var(--canvas); color:var(--ink);
          font-family:'Segoe UI Variable Text','Segoe UI',Arial,sans-serif; }
        [data-testid="stHeader"] { background:transparent; }
        [data-testid="stSidebar"], [data-testid="collapsedControl"] { display:none; }
        .block-container { max-width:1260px; padding:1.1rem 2.2rem 3.5rem; }
        h1, h2, h3 { color:var(--ink); letter-spacing:-.035em; }
        p, label, [data-testid="stCaptionContainer"] { color:var(--muted); }
        .eyebrow { color:var(--teal); font:650 .74rem/1.3 'Segoe UI',Arial,sans-serif;
          letter-spacing:.11em; margin-bottom:.35rem; text-transform:uppercase; }
        .brandbar { display:flex; align-items:center; gap:.75rem; min-height:54px;
          padding:.2rem 0; }
        .brand-rule { border-top:1px solid var(--line); margin:.7rem 0 2.4rem; }
        .topnav-active { background:var(--paper); border:1px solid var(--line); border-radius:999px;
          color:var(--pine); font-size:.82rem; font-weight:650; margin-left:auto; padding:.58rem 1rem;
          text-align:center; width:max-content; }
        .brand-mark { display:grid; place-items:center; width:42px; height:42px; flex:0 0 42px;
          color:#F7F5EA; background:var(--pine); border-radius:14px 14px 14px 4px;
          font:600 1.25rem/1 Georgia,'Times New Roman',serif; }
        .brand-name { color:var(--ink); font-size:1rem; font-weight:700; letter-spacing:-.02em; }
        .brand-tag { color:var(--muted); font-size:.65rem; letter-spacing:.13em; text-transform:uppercase; }
        .hero-grid { display:grid; grid-template-columns:minmax(0,1.45fr) minmax(230px,.55fr);
          gap:2rem; align-items:end; margin:0 0 1.8rem; }
        .hero-kicker { color:var(--teal); font-size:.73rem; font-weight:700; letter-spacing:.12em;
          margin-bottom:.8rem; text-transform:uppercase; }
        .hero-title, .stMarkdown h1.hero-title { color:var(--pine) !important;
          font-family:Georgia,'Times New Roman',serif !important; font-size:clamp(2.9rem,6.4vw,5.2rem) !important;
          font-weight:500 !important; line-height:.98 !important; letter-spacing:-.055em !important;
          margin:0 !important; max-width:760px; }
        .hero-copy { color:var(--muted); font-size:1.02rem; line-height:1.65; max-width:650px; margin:.85rem 0 0; }
        .hero-aside { border-left:2px solid var(--amber); color:var(--muted); font-size:.9rem;
          line-height:1.55; margin-bottom:.2rem; padding:.3rem 0 .3rem 1rem; }
        .hero-aside strong { color:var(--ink); display:block; font-size:.78rem; margin-bottom:.4rem; }
        [data-testid="stForm"] { background:var(--paper); border:1px solid var(--line); border-radius:18px;
          box-shadow:0 12px 36px rgba(24,58,48,.045); padding:1rem 1.3rem .4rem; }
        .lookup-shell-title { color:var(--ink); font-size:.95rem; font-weight:700; margin:.1rem 0 .2rem; }
        .lookup-shell-copy { color:var(--muted); font-size:.83rem; margin:0 0 .5rem; }
        .lookup-result { background:var(--paper); border:1px solid var(--line); border-radius:14px;
          padding:1.05rem 1.25rem; margin:.7rem 0; }
        .lookup-result--found { border-left:4px solid var(--teal); }
        .lookup-result--empty { border-left:4px solid var(--amber); }
        .lookup-result__title { color:var(--ink); font-size:1.06rem; font-weight:700; }
        .lookup-result__copy { color:var(--muted); line-height:1.55; margin:.35rem 0 0; }
        .result-heading { color:var(--ink); font-size:1.05rem; font-weight:700; margin:1.8rem 0 .35rem; }
        .result-subtitle { color:var(--muted); font-size:.88rem; margin:0 0 .75rem; }
        .status-strip { background:#EAF0E9; border:1px solid var(--line); border-left:4px solid var(--teal);
          border-radius:10px; padding:12px 16px; margin:.6rem 0 1.1rem; }
        .trace { border-left:2px solid var(--line); padding:.1rem 0 .1rem 1rem; margin:.35rem 0 .9rem; }
        .trace-item { position:relative; padding:.65rem .85rem; margin:.45rem 0; background:var(--paper);
          border:1px solid var(--line); border-radius:10px; }
        .trace-item:before { content:''; position:absolute; width:8px; height:8px; left:-1.36rem;
          top:1rem; background:var(--teal); border:2px solid var(--canvas); border-radius:50%; }
        .trace-stage { color:var(--teal); font-size:.76rem; font-weight:650; }
        .trace-message { color:var(--ink); margin-top:.2rem; overflow-wrap:anywhere; }
        div[data-testid="stMetric"] { background:var(--paper); border:1px solid var(--line); border-radius:12px;
          padding:14px 16px; }
        div[data-testid="stMetricLabel"] { color:var(--muted); }
        div[data-testid="stMetricValue"] { color:var(--ink); font-variant-numeric:tabular-nums; }
        .stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] button {
          cursor:pointer; transition:background-color 180ms ease,border-color 180ms ease,color 180ms ease;
          border-radius:999px; min-height:42px; }
        .stButton > button[kind="primary"], [data-testid="stFormSubmitButton"] button,
        button[data-testid="stBaseButton-primary"] {
          background:var(--pine) !important; border-color:var(--pine) !important; color:#FFFFFF !important;
        }
        .stButton > button:hover, .stDownloadButton > button:hover { border-color:var(--teal); color:var(--teal); }
        .stTabs [data-baseweb="tab-highlight"] { background:var(--teal); }
        .stTabs button[role="tab"][aria-selected="true"] { color:var(--teal); }
        .stButton > button:focus-visible, .stDownloadButton > button:focus-visible,
        input:focus-visible, textarea:focus-visible { outline:3px solid var(--teal) !important;
          outline-offset:2px !important; }
        [data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:12px; }
        div[data-testid="stRadio"] [role="radiogroup"] { justify-content:flex-end; gap:.25rem;
          background:#E8EEE8; border-radius:999px; padding:.24rem; }
        div[data-testid="stRadio"] label { border-radius:999px; padding:.32rem .8rem; }
        div[data-testid="stRadio"] label:has(input:checked) { background:var(--paper); }
        .app-footer { border-top:1px solid var(--line); color:var(--muted); font-size:.78rem;
          margin-top:3rem; padding-top:1rem; }
        @media (max-width: 768px) {
          .block-container { padding:1rem 1rem 2.5rem; }
          .brandbar { margin-bottom:1.7rem; }
          .hero-grid { grid-template-columns:1fr; gap:.8rem; margin-bottom:1.2rem; }
          .hero-title, .stMarkdown h1.hero-title { font-size:clamp(2.7rem,12vw,4rem) !important; }
          .hero-aside { max-width:520px; }
          [data-testid="stForm"] { padding:.8rem .9rem .35rem; }
        }
        @media (prefers-reduced-motion: reduce) {
          *, *::before, *::after { scroll-behavior:auto !important; animation:none !important;
            transition:none !important; }
        }
        </style>""",
        unsafe_allow_html=True,
    )


def _render_trace(st, events):
    if not events:
        st.caption("Chưa có bước chạy nào trong phiên UI này.")
        return
    items = []
    for event in events:
        stage = html.escape(str(event.get("stage", "step")))
        message = html.escape(str(event.get("message", "")))
        items.append(
            f'<div class="trace-item"><div class="trace-stage">{stage}</div>'
            f'<div class="trace-message">{message}</div></div>'
        )
    st.markdown('<div class="trace">' + "".join(items) + "</div>", unsafe_allow_html=True)


def _file_downloads(st, files):
    labels = {
        "xlsx": (
            "Excel workbook",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        "listings_csv": ("Listings CSV", "text/csv"),
        "statistics_csv": ("Ward statistics CSV", "text/csv"),
        "listings_json": ("Listings JSON", "application/json"),
        "daily_html": ("Daily report HTML", "text/html"),
        "daily_json": ("Daily report JSON", "application/json"),
        "national_listings_csv": ("National listings CSV", "text/csv"),
        "national_listings_json": ("National listings JSON", "application/json"),
        "national_statistics_csv": ("National price statistics CSV", "text/csv"),
    }
    columns = st.columns(3)
    index = 0
    for key, (label, mime) in labels.items():
        path = files.get(key)
        if not path:
            continue
        path = Path(path)
        if not path.is_file():
            continue
        with columns[index % len(columns)]:
            st.download_button(
                label,
                data=path.read_bytes(),
                file_name=path.name,
                mime=mime,
                key=f"download_{key}",
                use_container_width=True,
            )
        index += 1


def _show_overview(st, settings, data):
    st.subheader("Tổng quan dữ liệu")
    remaining = max(0, settings.max_calls_per_month - data["calls_used"])
    columns = st.columns(2)
    columns[0].metric("Tin đang theo dõi", f"{data['tracked']} / {settings.max_total_listings}")
    columns[1].metric("Phường trong whitelist", len(data["wards"]))
    columns = st.columns(2)
    columns[0].metric("Tin đủ điều kiện thống kê", len(data["listings"]))
    columns[1].metric("Lượt prompt tháng này", f"Còn {remaining} / {settings.max_calls_per_month}")

    key_status = "configured" if settings.api_key else "not configured"
    st.markdown(
        f'<div class="status-strip"><strong>Gemini:</strong> {html.escape(settings.model)} · '
        f"API key {key_status} · <strong>Chỉ gọi API live sau khi xác nhận trong tab Pipeline.</strong>"
        "</div>",
        unsafe_allow_html=True,
    )

    latest = data["recent"]
    if latest:
        first = latest[0]
        st.markdown("#### Lần tìm kiếm phường gần nhất")
        columns = st.columns(2)
        columns[0].metric("Status", first["status"])
        columns[1].metric("Phường", first["ward_name"] or first["ward_code"])
        columns = st.columns(2)
        columns[0].metric("Mới / cập nhật", f"{first['accepted_count']} / {first['updated_count']}")
        columns[1].metric("Truy vấn Search", first["search_queries"])
        st.caption(
            f"Bắt đầu lúc {first['started_at']} UTC · Search grounding: "
            f"{'đã dùng' if first['grounding_used'] else 'không được báo'}"
        )
        if first["error"]:
            st.warning(first["error"])
    else:
        st.info("Chưa có lần tìm tin nào. Hãy chạy xem trước để kiểm tra các phường được chọn.")

    st.markdown("#### Hoạt động pipeline gần đây")
    if latest:
        st.dataframe(latest, hide_index=True, use_container_width=True)
    else:
        st.caption("Lịch sử tìm kiếm sẽ xuất hiện ở đây sau khi chạy pipeline.")

    st.markdown("#### Thống kê theo phường và loại bất động sản")
    if data["statistics"]:
        st.dataframe(data["statistics"], hide_index=True, use_container_width=True)
    else:
        st.info("Thống kê xuất hiện sau khi thu thập được tin rao đủ nguồn và dữ liệu.")


def _show_run_tab(st, settings, data):
    st.subheader("Chạy pipeline thu thập tin rao")
    selection = data["selection"]
    capacity = selection["capacity"]
    recommended = selection["selected"]
    display_names = {
        ward.code: f"{ward.name} · {ward.province} [{ward.code}]" for ward in data["wards"]
    }
    default_codes = [ward.code for ward in recommended]
    st.caption(
        f"Hệ thống ưu tiên phường có ít tin đang theo dõi và lâu chưa tìm lại. "
        f"Lượt này có thể xử lý {capacity} phường; còn {selection['calls_left']} prompt trong tháng. "
        "Mỗi prompt có thể phát sinh nhiều truy vấn Google Search."
    )
    selected_codes = st.multiselect(
        "Chọn phường trong whitelist",
        options=list(display_names),
        default=default_codes,
        format_func=lambda code: display_names[code],
        max_selections=capacity or None,
        disabled=not data["wards"] or capacity == 0,
        help="Chỉ chọn được các phường active đã import vào whitelist.",
    )

    chosen_preview = preview_listing_selection_for_codes(data, settings, selected_codes)
    left, right = st.columns([1, 1])
    with left:
        if st.button(
            "Xem trước các bước",
            key="preview_pipeline",
            disabled=not data["wards"],
            use_container_width=True,
        ):
            if not chosen_preview["selected"] and chosen_preview["calls_left"] == 0:
                selection_message = "Không có phường được gọi: cap prompt Gemini tháng này đã hết."
            elif not chosen_preview["selected"]:
                selection_message = "Chưa chọn phường nào để chạy."
            else:
                selection_message = (
                    f"Đã chọn {len(chosen_preview['selected'])} phường; "
                    f"còn {chosen_preview['calls_left']} prompt trong tháng"
                )
            events = [
                {
                    "stage": "preflight",
                    "message": f"Đã tải {len(data['wards'])} phường active trong whitelist",
                },
                {"stage": "selection", "message": selection_message},
                {
                    "stage": "dry-run",
                    "message": "Không gọi Gemini, không ghi DB, không gửi email và không thay đổi lịch chạy.",
                },
            ]
            st.session_state["last_pipeline_events"] = events
            st.session_state["last_pipeline_result"] = {
                "mode": "XEM TRƯỚC",
                "selected_wards": [
                    {"ward_code": ward.code, "ward_name": ward.name, "province": ward.province}
                    for ward in chosen_preview["selected"]
                ],
                "monthly_prompt_slots_remaining": chosen_preview["calls_left"],
                "network_request": False,
                "database_changed": False,
            }
    with right:
        st.markdown(
            f"**API key:** {'configured' if settings.api_key else 'missing'}  \n"
            f"**Model:** `{settings.model}`  \n"
            f"**Request cap:** {settings.max_calls_per_month} prompt(s) per month"
        )

    if st.session_state.get("last_pipeline_result"):
        st.markdown("#### Kết quả gần nhất")
        st.json(st.session_state["last_pipeline_result"], expanded=True)
        _render_trace(st, st.session_state.get("last_pipeline_events", []))

    st.markdown("#### Chạy Gemini thật")
    st.warning(
        "Thao tác này gửi prompt tìm tin rao đến Gemini kèm Search grounding. "
        "Giới hạn prompt không phải giới hạn hóa đơn hay số truy vấn Search. Hãy kiểm tra quota và giá trước."
    )
    with st.form("live_run_form"):
        acknowledge = st.checkbox(
            "Tôi đã kiểm tra quyền truy cập, quota và chi phí của Gemini; tôi đồng ý chạy thật cho các phường đã chọn."
        )
        submitted = st.form_submit_button(
            "Chạy Gemini cho các phường đã chọn",
            type="primary",
            disabled=not selected_codes or not settings.api_key or capacity == 0,
            use_container_width=True,
        )
    if submitted and not acknowledge:
        st.error("Đánh dấu ô xác nhận ở trên trước khi bắt đầu gọi Gemini thật.")
    elif submitted and acknowledge:
        from wardprice.gemini import GeminiResearcher

        progress = st.progress(0, text="Đang kiểm tra trước khi chạy…")
        trace = st.empty()
        events = []

        def on_progress(event):
            events.append(event)
            st.session_state["last_pipeline_events"] = list(events)
            value = event.get("progress")
            if value is not None:
                progress.progress(min(100, max(0, int(value * 100))), text=event["message"][:120])
            _render_trace(trace, events)

        try:
            db = connect(DEFAULT_DB)
            try:
                result = run_listing_cycle(
                    db,
                    settings,
                    GeminiResearcher(settings.api_key, settings.model),
                    selected_ward_codes=selected_codes,
                    logger=None,
                    progress_callback=on_progress,
                )
                output_files = export(db, DEFAULT_OUTPUT)
            finally:
                db.close()
            st.session_state["last_pipeline_result"] = {"mode": "LIVE", **result}
            st.session_state["output_files"] = {
                key: str(path) for key, path in output_files.items()
            }
            summary = (
                f"Đã kết thúc: thêm {result['inserted']} tin, cập nhật {result['updated']} tin, "
                f"loại {result['rejected']} tin, lỗi {result['failed']} phường. "
                "Excel và CSV đã được làm mới."
            )
            if result["stopped_after_429"]:
                summary += (
                    f" Gemini trả HTTP 429; đã dừng và không gửi request cho "
                    f"{result['not_attempted']} phường còn lại. Kiểm tra quota/billing trong Google AI Studio."
                )
            if result["failed"]:
                st.warning(summary)
            else:
                st.success(summary)
            st.rerun()
        except Exception as exc:  # noqa: BLE001 - show safe local diagnostic, never credentials
            st.session_state["last_pipeline_events"] = list(events)
            safe_message = _redact_error(exc, settings.api_key)
            st.session_state["last_pipeline_result"] = {"mode": "LIVE", "error": safe_message}
            st.error(f"Pipeline chưa hoàn tất: {safe_message}")


def preview_listing_selection_for_codes(data, settings, selected_codes):
    """Compute the run preview from the local DB without creating a run record."""
    db = connect(DEFAULT_DB)
    try:
        return preview_listing_selection(db, settings, selected_codes)
    finally:
        db.close()


def _show_data_tab(st, data):
    st.subheader("Tin rao và thống kê bằng Python")
    st.caption(
        "Chỉ tin active có nguồn trong whitelist đã import xuất hiện ở đây. "
        "Valuation AI_ESTIMATE cũ được lưu riêng và không tham gia thống kê."
    )
    filters = st.columns(2)
    wards = sorted({row["ward_name"] for row in data["listings"]})
    selected_wards = filters[0].multiselect("Phường", wards, default=wards)
    selected_types = filters[1].multiselect(
        "Loại bất động sản", list(PROPERTY_TYPES), default=list(PROPERTY_TYPES)
    )
    visible = [
        row
        for row in data["listings"]
        if row["ward_name"] in selected_wards and row["property_type"] in selected_types
    ]
    if visible:
        st.dataframe(
            visible,
            hide_index=True,
            use_container_width=True,
            column_config={
                "source_url": st.column_config.LinkColumn("Nguồn", display_text="Mở tin rao"),
                "price_vnd": st.column_config.NumberColumn("Giá (VND)", format="%.0f"),
                "area_m2": st.column_config.NumberColumn("Diện tích (m²)", format="%.2f"),
                "price_per_m2": st.column_config.NumberColumn("Giá / m² (VND)", format="%.0f"),
            },
        )
    else:
        st.info("Chưa có tin rao phù hợp với bộ lọc này.")

    st.markdown("#### Thống kê riêng theo phường và loại bất động sản")
    if data["statistics"]:
        filtered_stats = [
            row
            for row in data["statistics"]
            if row["ward_name"] in selected_wards and row["property_type"] in selected_types
        ]
        st.dataframe(
            filtered_stats,
            hide_index=True,
            use_container_width=True,
            column_config={
                "mean_price_per_m2": st.column_config.NumberColumn(
                    "Trung bình (VND/m²)", format="%.0f"
                ),
                "median_price_per_m2": st.column_config.NumberColumn(
                    "Trung vị (VND/m²)", format="%.0f"
                ),
                "min_price_per_m2": st.column_config.NumberColumn(
                    "Thấp nhất (VND/m²)", format="%.0f"
                ),
                "max_price_per_m2": st.column_config.NumberColumn(
                    "Cao nhất (VND/m²)", format="%.0f"
                ),
            },
        )
    else:
        st.caption("Chưa có nhóm tin đủ điều kiện để thống kê.")


def _show_outputs_tab(st, settings):
    st.subheader("Xuất dữ liệu và báo cáo hằng ngày")
    st.caption(f"Thư mục output: `{DEFAULT_OUTPUT}`")
    export_col, preview_col = st.columns(2)
    with export_col:
        generate = st.button("Tạo CSV / Excel / báo cáo", type="primary", key="generate_exports")
    with preview_col:
        prepare_email = st.button("Chuẩn bị Gmail preview (dry-run)", key="prepare_email_preview")

    if generate or prepare_email:
        db = connect(DEFAULT_DB)
        try:
            files = export(db, DEFAULT_OUTPUT)
        finally:
            db.close()
        st.session_state["output_files"] = {key: str(path) for key, path in files.items()}
        if generate:
            st.success("Đã ghi các file CSV, Excel và báo cáo ngày vào outputs.")
        if prepare_email:
            date = Path(files["daily_html"]).stem.removeprefix("daily_report_")
            preview = dry_run_report(
                settings,
                files,
                f"WardPriceDaily — daily listing report {date}",
            )
            preview.pop("message")
            st.session_state["email_preview"] = preview
            st.success("Đã chuẩn bị nội dung Gmail cục bộ. Không kết nối SMTP và không gửi email.")

    preview = st.session_state.get("email_preview")
    if preview:
        st.markdown("#### Gmail preview (chỉ dry-run)")
        st.json(preview, expanded=True)
    files = st.session_state.get("output_files", {})
    if files:
        st.markdown("#### Tải file")
        _file_downloads(st, files)
    else:
        st.info("Tạo export để hiện các liên kết tải file.")
    st.caption("Dashboard không có nút gửi email thật hoặc kích hoạt Windows Task Scheduler.")


def _parse_price_query(query, provinces):
    """Extract a locality and optional filters from a short Vietnamese question."""
    normalized = normalize_admin_name(query)
    inferred_property = None
    property_phrases = (
        ("NHA_RIENG", ("nha rieng", "nha pho", "nha o rieng le")),
        ("CHUNG_CU", ("chung cu", "can ho")),
        ("DAT_O", ("dat o", "dat tho cu")),
    )
    for property_type, phrases in property_phrases:
        if any(phrase in normalized for phrase in phrases):
            inferred_property = property_type
            for phrase in phrases:
                normalized = re.sub(rf"\b{re.escape(phrase)}\b", " ", normalized)
            break
    inferred_province = None
    province_terms = []
    for province in provinces:
        province_name = normalize_admin_name(province)
        province_terms.append((province_name, province))
        for prefix in ("thanh pho ", "tinh "):
            if province_name.startswith(prefix):
                province_terms.append((province_name[len(prefix) :], province))
    for term, province in sorted(province_terms, key=lambda item: len(item[0]), reverse=True):
        if len(term) >= 4 and term in normalized:
            inferred_province = province
            normalized = re.sub(rf"\b{re.escape(term)}\b", " ", normalized, count=1)
            break
    for phrase in (
        "cho toi biet",
        "toi muon xem",
        "bat dong san",
        "muc gia",
        "gia",
        "bds",
        "tai",
        "o",
        "thuoc",
        "phuong",
        "xa",
        "thi tran",
        "dac khu",
        "tinh",
        "thanh pho",
        "quan",
        "huyen",
        "xem",
    ):
        normalized = re.sub(rf"\b{re.escape(phrase)}\b", " ", normalized)
    return " ".join(normalized.split()), inferred_province, inferred_property


def _show_national_lookup(st):
    st.markdown(
        """<div class="lookup-intro">
          <div class="hero-kicker">Thị trường nhà ở · Việt Nam</div>
          <div class="hero-grid">
            <div><h1 class="hero-title">Sổ tay giá,<br>theo từng phường.</h1>
              <p class="hero-copy">Tra cứu giá rao theo địa bàn, loại bất động sản và nguồn dữ liệu.
              Mỗi con số đều dựa trên tin rao đã được xác minh.</p></div>
            <div class="hero-aside"><strong>Cách đọc dữ liệu</strong>
              Giá/m² được tính bằng Python từ listing có nguồn. Nhà riêng, đất ở và chung cư
              luôn được thống kê riêng.</div>
          </div>
        </div>""",
        unsafe_allow_html=True,
    )
    db = connect(DEFAULT_DB)
    try:
        provinces = [
            row[0]
            for row in db.execute(
                """SELECT DISTINCT province_name FROM administrative_units
                   WHERE is_current=1 AND administrative_level='COMMUNE'
                   ORDER BY province_name"""
            ).fetchall()
        ]
        if "national_search_results" not in st.session_state:
            st.session_state["national_search_query"] = ""
            st.session_state["national_search_results"] = []
            st.session_state["national_search_filters"] = {
                "property_type": None,
                "area_basis": None,
            }
            st.session_state["national_search_meta"] = {}
    finally:
        db.close()
    st.markdown(
        '<div class="lookup-shell-title">Bạn muốn xem giá ở đâu?</div>', unsafe_allow_html=True
    )
    st.markdown(
        '<p class="lookup-shell-copy">Nhập tên phường/xã hoặc câu hỏi ngắn để bắt đầu.</p>',
        unsafe_allow_html=True,
    )
    with st.form("national_search_form"):
        query = st.text_input(
            "Địa bàn hoặc câu hỏi",
            key="national_search_query",
            placeholder="Ví dụ: Nhà riêng ở Ba Đình, Hà Nội",
        )
        province_col, type_col = st.columns(2)
        with province_col:
            province = st.selectbox("Tỉnh/thành", ["Tất cả", *provinces])
        with type_col:
            property_type = st.selectbox(
                "Loại bất động sản",
                [None, *PROPERTY_TYPES],
                format_func=lambda value: {
                    None: "Tất cả loại",
                    "DAT_O": "Đất ở",
                    "NHA_RIENG": "Nhà riêng",
                    "CHUNG_CU": "Chung cư",
                }[value],
            )
        area_basis = st.selectbox(
            "Cơ sở diện tích",
            [None, *sorted(AREA_BASES)],
            format_func=lambda value: {
                None: "Tất cả diện tích",
                "LAND_AREA": "Diện tích đất",
                "FLOOR_AREA": "Diện tích sàn",
                "USABLE_AREA": "Diện tích sử dụng",
                "OTHER": "Khác",
            }[value],
        )
        submitted = st.form_submit_button("Tra cứu giá")
    if submitted:
        location_query, inferred_province, inferred_property = _parse_price_query(query, provinces)
        selected_province = province if province != "Tất cả" else inferred_province
        selected_property = property_type or inferred_property
        db = connect(DEFAULT_DB)
        try:
            results = (
                WardLookupService(db).search(
                    location_query,
                    province=selected_province,
                    include_historical=True,
                    limit=50,
                )
                if location_query
                else []
            )
        finally:
            db.close()
        st.session_state["national_search_results"] = results
        st.session_state["national_search_filters"] = {
            "property_type": selected_property,
            "area_basis": area_basis,
        }
        st.session_state["national_search_meta"] = {
            "province": selected_province,
            "property_type": selected_property,
        }
        st.session_state.pop("national_selected_result", None)

    results = st.session_state.get("national_search_results", [])
    filters = st.session_state.get("national_search_filters", {})
    meta = st.session_state.get("national_search_meta", {})
    if not results:
        db = connect(DEFAULT_DB)
        try:
            status = national_coverage(db)["registry_status"]
        finally:
            db.close()
        if status == "NATIONWIDE_READY_AWAITING_DATA":
            st.info("Danh mục toàn quốc chưa được nhập. Chạy lệnh admin-import trong README.")
        elif submitted or st.session_state.get("national_search_results") == []:
            if submitted:
                st.markdown(
                    """<div class="lookup-result lookup-result--empty">
                      <div class="lookup-result__title">Chưa tìm thấy địa bàn phù hợp</div>
                      <p class="lookup-result__copy">Kiểm tra cách viết, thử tên có dấu hoặc thêm tỉnh/thành
                      để phân biệt các địa bàn trùng tên.</p></div>""",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    """<div class="lookup-result">
                      <div class="lookup-result__title">Bắt đầu bằng một phường hoặc xã</div>
                      <p class="lookup-result__copy">Ví dụ: “Ba Đình, Hà Nội” hoặc “nhà riêng ở phường Thủ Đức”.
                      Bạn sẽ chọn địa bàn chính xác trước khi xem số liệu.</p></div>""",
                    unsafe_allow_html=True,
                )
        return
    if meta.get("property_type") or meta.get("province"):
        recognized = []
        if meta.get("property_type"):
            recognized.append(
                {
                    "DAT_O": "Đất ở",
                    "NHA_RIENG": "Nhà riêng",
                    "CHUNG_CU": "Chung cư",
                }.get(meta["property_type"], meta["property_type"])
            )
        if meta.get("province"):
            recognized.append(meta["province"])
        st.caption(f"Đã nhận diện: {' · '.join(recognized)}")

    st.markdown(
        f'<div class="result-heading">Địa bàn phù hợp <span class="result-subtitle">· {len(results)} lựa chọn</span></div>',
        unsafe_allow_html=True,
    )

    def _label(row):
        match = row.get("matched_alias")
        suffix = f" · tên cũ: {match}" if match else ""
        return f"{row['name']} · {row.get('province') or 'chưa rõ tỉnh'}{suffix}"

    ambiguous = len(results) > 1
    result_options = [None, *range(len(results))] if ambiguous else list(range(len(results)))
    selected = st.selectbox(
        "Chọn đúng địa bàn",
        options=result_options,
        index=0,
        format_func=lambda index: (
            "Chọn tỉnh/thành để phân biệt" if index is None else _label(results[index])
        ),
        key="national_selected_result",
    )
    if selected is None:
        st.info(
            "Tên này khớp với nhiều địa bàn. Chọn đúng tỉnh/thành để xem dữ liệu; "
            "hệ thống không tự chọn theo thứ tự."
        )
        return
    unit = results[selected]
    st.markdown(
        f"""<div class="lookup-result lookup-result--found">
          <div class="lookup-result__title">{html.escape(str(unit["name"]))} ·
          {html.escape(str(unit.get("province") or "Chưa rõ tỉnh/thành"))}</div>
          <p class="lookup-result__copy">Địa bàn đã được đối chiếu với danh mục hành chính.
          {("Tên cũ được nhận diện: " + html.escape(str(unit["matched_alias"])) + ".") if unit.get("matched_alias") else ""}</p>
        </div>""",
        unsafe_allow_html=True,
    )

    db = connect(DEFAULT_DB)
    try:
        lookup_query = unit.get("administrative_code") or unit.get("name", "")
        lookup = WardPriceLookupService(db).lookup(
            lookup_query,
            province=unit.get("province") or None,
            target_rank=unit.get("target_rank") if unit.get("unit_id") is None else None,
            property_type=filters.get("property_type"),
            area_basis=filters.get("area_basis"),
        )
        history = (
            WardPriceLookupService(db).history(
                unit["unit_id"],
                property_type=filters.get("property_type"),
                area_basis=filters.get("area_basis"),
                limit=12,
            )
            if unit.get("unit_id") is not None and lookup.get("statistics")
            else []
        )
    finally:
        db.close()
    status_labels = {
        "FOUND": "Có dữ liệu giá",
        "STALE_DATA": "Dữ liệu đã cũ",
        "NO_PRICE_DATA": "Chưa có dữ liệu giá",
        "UNVERIFIED_ONLY": "Chỉ có tin chưa xác minh",
        "EXTERNAL_PROVIDER_NOT_CONFIGURED": "Chưa cấu hình nguồn cập nhật",
        "NOT_FOUND": "Chưa tìm thấy địa bàn",
        "AMBIGUOUS": "Cần chọn địa bàn cụ thể",
    }
    st.markdown(
        f'<div class="result-heading">Giá rao trong khu vực</div>'
        f'<p class="result-subtitle">{html.escape(status_labels.get(lookup["status"], lookup["status"]))} · '
        "chỉ tính tin có nguồn đã xác minh</p>",
        unsafe_allow_html=True,
    )
    property_labels = {
        "DAT_O": "Đất ở",
        "NHA_RIENG": "Nhà riêng",
        "CHUNG_CU": "Chung cư",
    }
    area_basis_labels = {
        "LAND_AREA": "Diện tích đất",
        "FLOOR_AREA": "Diện tích sàn",
        "USABLE_AREA": "Diện tích sử dụng",
        "OTHER": "Cơ sở khác",
    }
    if lookup["status"] == "NO_PRICE_DATA":
        st.markdown(
            """<div class="lookup-result">
              <div class="lookup-result__title">Chưa có mẫu tin đủ căn cứ</div>
              <p class="lookup-result__copy">Địa bàn đã được nhận diện. Hiện chưa có listing
              xác minh đủ nguồn để tính giá; sổ tay không tự ước tính giá thay cho dữ liệu.</p>
            </div>""",
            unsafe_allow_html=True,
        )
    elif lookup["status"] == "UNVERIFIED_ONLY":
        st.markdown(
            f"""<div class="lookup-result lookup-result--empty">
              <div class="lookup-result__title">Có {int(lookup.get("candidate_count", 0))} tin đang chờ xác minh</div>
              <p class="lookup-result__copy">Các tin này chưa được tính vào thống kê. Giá chỉ hiển thị
              sau khi nguồn, địa bàn, giá và diện tích được kiểm tra.</p></div>""",
            unsafe_allow_html=True,
        )
    elif lookup["status"] == "STALE_DATA":
        st.warning("Dữ liệu đã cũ. Kiểm tra ngày quan sát và nguồn trước khi tham khảo.")
    elif lookup["status"] == "EXTERNAL_PROVIDER_NOT_CONFIGURED":
        st.info("Không có nguồn cập nhật bên ngoài được cấu hình.")
    if lookup.get("statistics"):
        for statistic in lookup["statistics"]:
            st.markdown(
                f'<div class="result-heading">{html.escape(property_labels.get(statistic["property_type"], statistic["property_type"]))}</div>'
                f'<p class="result-subtitle">{html.escape(area_basis_labels.get(statistic["area_basis"], statistic["area_basis"]))}</p>',
                unsafe_allow_html=True,
            )
            columns = st.columns(2)
            columns[0].metric(
                "Trung vị / m²",
                f"{statistic['median_price_per_m2']:,.0f} đ"
                if statistic.get("median_price_per_m2") is not None
                else "—",
            )
            columns[1].metric(
                "Trung bình / m²",
                f"{statistic['mean_price_per_m2']:,.0f} đ"
                if statistic.get("mean_price_per_m2") is not None
                else "—",
            )
            columns = st.columns(2)
            columns[0].metric("Số tin", statistic.get("sample_count", 0))
            columns[1].metric("Cập nhật", statistic.get("latest_observation_at") or "—")
        st.caption(
            "Đây là giá rao, không phải giá giao dịch. Mean và median được tính bằng Python; "
            "mỗi loại bất động sản và cơ sở diện tích được tính riêng."
        )
        if history:
            st.markdown("#### Tin rao trong mẫu")
            st.dataframe(
                history,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "source_url": st.column_config.LinkColumn("Nguồn tin", display_text="Mở tin"),
                    "listing_id": st.column_config.TextColumn("Mã tin"),
                    "property_type": st.column_config.TextColumn("Loại BĐS"),
                    "area_basis": st.column_config.TextColumn("Cơ sở diện tích"),
                    "observation_date": st.column_config.TextColumn("Ngày ghi nhận"),
                    "observed_price_vnd": st.column_config.NumberColumn("Giá rao (VND)"),
                    "observed_area_m2": st.column_config.NumberColumn("Diện tích (m²)"),
                    "price_per_m2": st.column_config.NumberColumn("Giá/m² (VND)"),
                    "evidence_status": st.column_config.TextColumn("Bằng chứng"),
                    "validation_status": st.column_config.TextColumn("Kiểm tra"),
                },
            )


def _show_national_coverage(st):
    st.subheader("Độ phủ toàn quốc")
    db = connect(DEFAULT_DB)
    try:
        report = national_coverage(db)
        collection_plan = national_collection_priorities(db, limit=25)
    finally:
        db.close()
    dataset = report.get("current_dataset") or {}
    administrative = report["administrative_coverage"]
    prices = report["price_coverage"]
    st.markdown(f"**Trạng thái registry:** `{report['registry_status']}`")
    if dataset:
        st.caption(
            f"Snapshot `{dataset['dataset_version']}` · ngày hiệu lực {dataset['as_of_date']} · "
            f"nguồn `{dataset['source_id']}`"
        )
    columns = st.columns(2)
    columns[0].metric("Tỉnh/thành hiện hành", administrative.get("province_count", 0))
    columns[1].metric("Phường/xã/đặc khu", administrative.get("commune_count", 0))
    columns = st.columns(2)
    columns[0].metric("Địa bàn có giá đã xác minh", prices.get("units_with_verified_price", 0))
    columns[1].metric("Địa bàn chưa có giá", prices.get("units_without_price_data", 0))
    columns = st.columns(2)
    columns[0].metric("Giá còn mới", prices.get("units_with_fresh_verified_price", 0))
    columns[1].metric("Giá đã cũ", prices.get("units_with_stale_price", 0))
    columns = st.columns(2)
    columns[0].metric(
        "Chỉ có ứng viên chưa xác minh", prices.get("units_with_unverified_candidates", 0)
    )
    columns[1].metric("Cập nhật giá gần nhất", prices.get("last_updated") or "—")
    priority = report.get("priority_targets", {})
    st.markdown("#### Độ phủ Top 50")
    st.write(
        f"{priority.get('mapped', 0)} / {priority.get('total', 0)} target đã liên kết "
        f"với địa bàn hiện hành; {priority.get('with_price_data', 0)} có dữ liệu giá đã xác minh."
    )
    st.markdown("#### Thứ tự ưu tiên thu thập")
    plan_columns = st.columns(3)
    for column, tier in zip(plan_columns, ("P0", "P1", "P2"), strict=True):
        column.metric(tier, collection_plan["tier_counts"][tier]["unit_count"])
    if collection_plan["unmapped_priority_target_count"]:
        st.info(
            f"{collection_plan['unmapped_priority_target_count']} Top 50 target chưa có mapping hiện hành; "
            "chúng được giữ trong danh sách rà soát và không tự gán vào P0 theo tên."
        )
    if collection_plan["units"]:
        st.dataframe(collection_plan["units"], hide_index=True, use_container_width=True)
    else:
        st.caption("Chưa có danh mục hiện hành để tạo kế hoạch thu thập.")
    st.markdown("#### Độ phủ theo tỉnh/thành")
    if report.get("by_province"):
        st.dataframe(report["by_province"], hide_index=True, use_container_width=True)
    else:
        st.info("Chưa có snapshot danh mục hành chính hiện hành.")


def _render_app_header(st, admin_enabled):
    brand_col, navigation_col = st.columns([4, 6], vertical_alignment="center")
    with brand_col:
        st.markdown(
            """<div class="brandbar">
              <div class="brand-mark" aria-hidden="true">₫</div>
              <div><div class="brand-name">WardPriceDaily</div>
              <div class="brand-tag">Sổ tay giá bất động sản</div></div>
            </div>""",
            unsafe_allow_html=True,
        )
    with navigation_col:
        if admin_enabled:
            view = st.radio(
                "Không gian",
                ["Tra cứu giá", "Quản trị"],
                horizontal=True,
                label_visibility="collapsed",
                key="workspace_view",
            )
        else:
            view = "Tra cứu giá"
            st.markdown(
                '<div class="topnav-active">Tra cứu giá</div>',
                unsafe_allow_html=True,
            )
    st.markdown('<div class="brand-rule"></div>', unsafe_allow_html=True)
    return view


def _capture_webpilot_submission():
    """Move submitted credentials out of widget state before the next render."""
    import streamlit as st

    cookie = str(st.session_state.pop("webpilot_cookie_input", "") or "").strip()
    token = str(st.session_state.pop("webpilot_token_input", "") or "").strip()
    consent = bool(st.session_state.pop("webpilot_live_confirm", False))
    rank = st.session_state.get("webpilot_rank")
    count = st.session_state.get("webpilot_count", 10)
    st.session_state.pop("webpilot_last_result", None)
    st.session_state.pop("webpilot_form_error", None)
    if not consent:
        st.session_state["webpilot_form_error"] = (
            "Đánh dấu xác nhận quyền sử dụng tài khoản và đồng ý gửi một request."
        )
    elif not cookie:
        st.session_state["webpilot_form_error"] = "Chưa nhập cookie 1PSID; chưa gửi request."
    else:
        st.session_state["_webpilot_pending"] = {
            "cookie": cookie,
            "token": token,
            "rank": int(rank),
            "count": int(count),
        }


def _render_webpilot_tab(st):
    try:
        from wardprice_webpilot.core import load_targets, make_prompt
        from wardprice_webpilot.ui_service import recent_candidates, run_live_collection
    except ImportError as exc:
        st.subheader("Thử thu thập bằng Gemini Web")
        st.error(f"Không nạp được module Gemini Web pilot trong môi trường UI này: {exc}")
        return

    st.subheader("Thử thu thập bằng Gemini Web")
    st.caption(
        "Một lần chạy gửi một request, tìm tối đa 10 tin cho một phường trong Top 50. "
        "Kết quả lưu ở sidecar pilot để kiểm tra; không nhập vào thống kê giá production."
    )
    try:
        targets = load_targets(DEFAULT_DB)
    except (FileNotFoundError, ValueError) as exc:
        st.error(f"Không đọc được danh sách 50 phường từ SQLite: {exc}")
        return

    rank = st.selectbox(
        "Phường cần thử",
        options=list(targets),
        index=10,
        format_func=lambda item_rank: (
            f"{item_rank:02d} · {targets[item_rank]['ward']} · "
            f"{targets[item_rank]['district']}, {targets[item_rank]['province']}"
        ),
        key="webpilot_rank",
    )
    count = st.slider(
        "Số tin tối đa trong request",
        min_value=1,
        max_value=10,
        value=10,
        key="webpilot_count",
        help="Nếu Gemini trả nhiều hơn mức này, phần dư sẽ không được nhập vào sidecar.",
    )
    prompt = make_prompt(targets[rank], count)
    with st.expander("Xem prompt trước khi chạy", expanded=False):
        st.code(prompt, language="text")

    st.markdown("#### Phiên Gemini Web")
    st.info(
        "Cookie được gửi tới Gemini Web để xác thực request và chỉ giữ tạm trong RAM của "
        "phiên Streamlit cục bộ. UI xóa trường sau khi bấm chạy; giá trị không được lưu "
        "vào file, SQLite hoặc log. Wrapper không chính thức không bảo đảm web search; "
        "mọi candidate vẫn UNVERIFIED cho tới khi bạn đối chiếu nguồn. Không dán cookie "
        "vào chat hoặc ảnh chụp màn hình."
    )
    with st.form("webpilot_live_form"):
        st.text_input(
            "Cookie 1PSID",
            type="password",
            key="webpilot_cookie_input",
            help="Giá trị Secure 1PSID trong Gemini cookie storage.",
        )
        st.text_input(
            "Cookie 1PSIDTS (nếu có)",
            type="password",
            key="webpilot_token_input",
            help="Có thể để trống nếu tài khoản không có cookie này.",
        )
        st.checkbox(
            "Tôi có quyền dùng phiên này và đồng ý gửi đúng một request Gemini Web cho lựa chọn trên.",
            key="webpilot_live_confirm",
        )
        st.form_submit_button(
            f"Chạy 1 request · tối đa {count} tin",
            type="primary",
            use_container_width=True,
            on_click=_capture_webpilot_submission,
        )

    if st.session_state.get("webpilot_form_error"):
        st.warning(st.session_state.pop("webpilot_form_error"))

    pending = st.session_state.pop("_webpilot_pending", None)
    if pending:
        stages: list[str] = []
        result: dict[str, object]
        with st.status("Đang chạy pilot…", expanded=True) as status_box:
            try:

                def on_progress(stage: str, message: str) -> None:
                    stages.append(stage)
                    status_box.write(message)

                result = run_live_collection(
                    targets_db=DEFAULT_DB,
                    audit_db=WEBPILOT_AUDIT_DB,
                    inbox=WEBPILOT_INBOX,
                    rank=pending["rank"],
                    count=pending["count"],
                    session_cookie=pending["cookie"],
                    session_token=pending["token"],
                    progress=on_progress,
                )
                result["steps"] = stages
                state = "complete" if result.get("status") == "COMPLETE" else "error"
                status_box.update(
                    label=(
                        "Đã hoàn tất request; kết quả đang chờ xác minh"
                        if state == "complete"
                        else "Request không hoàn tất"
                    ),
                    state=state,
                    expanded=True,
                )
            except Exception as exc:  # noqa: BLE001 - do not expose credentials in UI
                safe_error = str(exc)
                for secret_key in ("cookie", "token"):
                    secret = str(pending.get(secret_key) or "")
                    if secret:
                        safe_error = safe_error.replace(secret, "[redacted]")
                result = {
                    "status": "BLOCKED",
                    "error": safe_error[:1000],
                    "network_attempted": "gemini" in stages,
                    "production_database_written": False,
                    "steps": stages,
                }
                status_box.write(safe_error[:1000])
                status_box.update(label="Request bị chặn trước khi gọi mạng", state="error")
            finally:
                # Drop references as soon as the request returns.
                pending["cookie"] = ""
                pending["token"] = ""
        st.session_state["webpilot_last_result"] = result

    last_result = st.session_state.get("webpilot_last_result")
    if last_result:
        st.markdown("#### Kết quả gần nhất")
        if last_result.get("status") == "COMPLETE":
            metrics = st.columns(5)
            metrics[0].metric("Gemini trả", last_result.get("received", 0))
            metrics[1].metric("Candidate mới", last_result.get("inserted_candidates", 0))
            metrics[2].metric("Trùng", last_result.get("duplicates_exact", 0))
            metrics[3].metric("Bị loại", last_result.get("rejected", 0))
            metrics[4].metric("Nguồn xác minh", 0)
            st.caption(
                "Candidate được lưu trong audit nhưng vẫn UNVERIFIED. "
                "Không candidate nào được cộng vào giá trung bình hoặc dashboard tra cứu."
            )
        elif last_result.get("error"):
            st.error(str(last_result["error"]))
        st.json(last_result, expanded=True)

    st.markdown("#### Candidate audit của phường đang chọn")
    candidates = recent_candidates(WEBPILOT_AUDIT_DB, rank, limit=10)
    if candidates:
        st.dataframe(
            candidates,
            hide_index=True,
            use_container_width=True,
            column_config={
                "source_url": st.column_config.LinkColumn("Nguồn khai báo", display_text="Mở link"),
                "price_vnd": st.column_config.NumberColumn("Giá (VND)", format="%.0f"),
                "area_m2": st.column_config.NumberColumn("Diện tích (m²)", format="%.2f"),
                "price_per_m2": st.column_config.NumberColumn(
                    "Giá/m² (chưa xác minh)", format="%.0f"
                ),
                "verification_label": st.column_config.TextColumn("Trạng thái nguồn"),
                "evidence_status": st.column_config.TextColumn("Mức bằng chứng"),
                "source_url_type": st.column_config.TextColumn("Loại URL"),
                "review_status": st.column_config.TextColumn("Trạng thái rà soát"),
                "review_warning": st.column_config.TextColumn("Cảnh báo nguồn"),
                "geo_status": st.column_config.TextColumn("Địa bàn"),
                "quarantine_reason": st.column_config.TextColumn("Lý do cách ly"),
                "collected_at": st.column_config.TextColumn("Ngày thu thập"),
                "possible_duplicate": st.column_config.CheckboxColumn("Có thể trùng"),
            },
        )
        st.caption(
            "Mọi candidate trong bảng đều mang nhãn ‘Chưa xác minh nguồn’. "
            "URL danh mục được phân biệt với URL tin cụ thể; giá/m² chưa đi vào thống kê."
        )
    else:
        st.info("Chưa có candidate audit cho phường này.")


def _render_demo_app(st):
    """A read-only-by-default UI that never touches production tables or services."""
    st.markdown(
        """<div style="background:#123D35;color:#FFFEFA;border-left:5px solid #D5A34E;
        border-radius:8px 12px 12px 8px;padding:14px 18px;font-weight:800;
        letter-spacing:.02em;margin:0 0 18px">
        DEMO MODE — SYNTHETIC DATA · MỌI GIÁ BÊN DƯỚI LÀ SỐ GIẢ LẬP
        </div>""",
        unsafe_allow_html=True,
    )
    st.title("Sổ tay giá bất động sản · Bản demo")
    st.caption(
        "Dữ liệu phục vụ kiểm thử giao diện, SQLite và thống kê. Không phải tin rao thật, "
        "không phải giá thị trường; không gọi Gemini, web, Gmail hay scheduler thật."
    )
    with demo_database(DEFAULT_DB) as db:
        overview = demo_coverage(db)
        targets = demo_wards(db)
        scheduler_runs = [
            dict(row)
            for row in db.execute(
                "SELECT schedule_id,status,last_group_index,started_at,finished_at,error,network_called "
                "FROM demo_scheduler_runs ORDER BY started_at DESC"
            )
        ]

    lookup_tab, coverage_tab, history_tab, scheduler_tab = st.tabs(
        ["Tra cứu giá", "Độ phủ dữ liệu", "Tin rao & lịch sử", "Scheduler mock"]
    )
    with lookup_tab:
        st.subheader("Tra cứu trong 50 địa bàn demo")
        col_query, col_type = st.columns([2, 1])
        query = col_query.text_input(
            "Phường/xã, quận/huyện hoặc mã TOP50", value="Phường Bình Hưng Hòa"
        )
        type_choice = col_type.selectbox("Loại bất động sản", ["Tất cả", *PROPERTY_TYPES])
        selected_type = None if type_choice == "Tất cả" else type_choice
        with demo_database(DEFAULT_DB) as db:
            result = demo_lookup(db, query, property_type=selected_type)
        if result["status"] == "NOT_IN_TOP50":
            st.info("Địa bàn này không nằm trong Top 50 demo; chưa có giá trong bộ dữ liệu này.")
        elif result["status"] == "NOT_FOUND":
            st.info("Nhập tên địa bàn hoặc mã TOP50 để tra cứu.")
        elif result["status"] == "NO_PRICE_DATA":
            st.info("Đã nhận diện địa bàn nhưng chưa có listing trong demo database.")
        else:
            matching_targets = result["targets"]
            target_by_rank = {row["target_rank"]: row for row in matching_targets}
            selected_rank = st.selectbox(
                "Chọn địa bàn",
                list(target_by_rank),
                format_func=lambda rank: (
                    f"#{rank:02d} · {target_by_rank[rank]['ward_name']} · "
                    f"{target_by_rank[rank]['district']}, {target_by_rank[rank]['province']}"
                ),
                key="demo_lookup_target_rank",
            )
            selected_label = target_by_rank[selected_rank]
            st.markdown(
                f"**#{selected_label['target_rank']:02d} · {selected_label['ward_name']}**  "
                f"\n{selected_label['district']} · {selected_label['province']} · "
                f"Mã nội bộ {selected_label['ward_code']}"
            )
            for start in range(0, len(selected_label["statistics"]), 3):
                stat_group = selected_label["statistics"][start : start + 3]
                columns = st.columns(len(stat_group))
                for column, stat in zip(columns, stat_group):
                    column.metric(
                        f"{stat['property_type']} · mean giả lập",
                        f"{stat['mean_price_per_m2']:,.0f} ₫/m²",
                        f"Median {stat['median_price_per_m2']:,.0f} ₫/m²",
                    )
                    column.caption(f"{stat['listing_count']} tin · {stat['data_quality']}")
            if selected_label["listings"]:
                import pandas as pd

                st.dataframe(
                    pd.DataFrame(selected_label["listings"]),
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "price_vnd": st.column_config.NumberColumn(
                            "Giá giả lập (₫)", format="%.0f"
                        ),
                        "area_m2": st.column_config.NumberColumn("Diện tích (m²)", format="%.1f"),
                        "price_per_m2": st.column_config.NumberColumn(
                            "Giá giả lập/m² (₫)", format="%.0f"
                        ),
                    },
                )
                st.caption(
                    "Nguồn: DEMO_SYNTHETIC · trạng thái bằng chứng: UNVERIFIED · URL nguồn: không có"
                )

    with coverage_tab:
        st.subheader("Coverage Dashboard · dữ liệu giả lập")
        cols = st.columns(4)
        cols[0].metric("Địa bàn có trong registry", f"{overview['target_count']} / 50")
        cols[1].metric("Địa bàn có listing", f"{overview['wards_with_data']} / 50")
        cols[2].metric("Tin duy nhất", f"{overview['listings']} / {overview['listing_cap']}")
        cols[3].metric("Quan sát hằng ngày", overview["daily_observations"])
        import pandas as pd

        st.bar_chart(
            pd.DataFrame(
                [
                    {"Loại BĐS": kind, "Số tin giả lập": count}
                    for kind, count in overview["property_type_counts"].items()
                ]
            ).set_index("Loại BĐS")
        )
        st.caption(f"{overview['statistics_groups']} nhóm thống kê phường/xã × loại BĐS")
        st.dataframe(pd.DataFrame(targets), hide_index=True, use_container_width=True)

    with history_tab:
        st.subheader("Tin rao và lịch sử quan sát")
        if targets:
            ward_by_rank = {row["target_rank"]: row for row in targets}
            selected_rank = st.selectbox(
                "Phường/xã",
                list(ward_by_rank),
                format_func=lambda rank: f"#{rank:02d} · {ward_by_rank[rank]['ward_name']}",
                key="demo_history_target",
            )
            history_type_choice = st.selectbox(
                "Lọc loại BĐS", ["Tất cả", *PROPERTY_TYPES], key="demo_history_type"
            )
            with demo_database(DEFAULT_DB) as db:
                history = demo_history(
                    db,
                    selected_rank,
                    property_type=None if history_type_choice == "Tất cả" else history_type_choice,
                )
            if history["observations"]:
                import pandas as pd

                st.dataframe(
                    pd.DataFrame(history["observations"]), hide_index=True, use_container_width=True
                )
                st.caption(
                    "Mỗi quan sát giữ ngày ghi nhận, giá/m², bằng chứng UNVERIFIED và run import."
                )
            else:
                st.info("Chưa có quan sát cho địa bàn/loại BĐS đã chọn.")

    with scheduler_tab:
        st.subheader("Mô phỏng pipeline hằng ngày · offline")
        st.write("50 địa bàn → 10 fixture batch → validation → dedup → SQLite → thống kê.")
        st.warning(
            "Nút này chỉ chạy fixture cục bộ. Không đăng ký Windows Task Scheduler và không gọi mạng."
        )
        if st.button("Chạy lại mock scheduler offline", type="primary"):
            schedule_id = f"ui-demo-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
            result = run_demo_scheduler(
                DEFAULT_DB, fixture_dir=FIXTURE_DIR, schedule_id=schedule_id
            )
            st.session_state["demo_scheduler_result"] = result
        if st.session_state.get("demo_scheduler_result"):
            st.json(st.session_state["demo_scheduler_result"])
        if scheduler_runs:
            import pandas as pd

            st.dataframe(pd.DataFrame(scheduler_runs), hide_index=True, use_container_width=True)
        else:
            st.info("Chưa có lần chạy mock nào được ghi nhận.")

    st.markdown(
        "<div style='border-top:1px solid #DCE4DB;margin-top:24px;padding-top:12px;color:#63736E'>"
        "DEMO MODE — dữ liệu giả lập được lưu trong state/ward_prices.demo.sqlite3. "
        "Không ảnh hưởng dữ liệu production.</div>",
        unsafe_allow_html=True,
    )


def _show_collection_monitoring(st):
    """Read-only operational view for the public-source collection pipeline."""
    _show_ingestion_pilot_monitoring(st)
    st.divider()
    st.subheader("Theo dõi thu thập dữ liệu web")
    st.caption("Giám sát nguồn, lượt chạy và chất lượng candidate. Tab này không khởi chạy crawler.")
    if not DEFAULT_DB.is_file():
        st.info("Chưa có SQLite production. Chạy `python -m wardprice collection-init` để khởi tạo.")
        return
    db = sqlite3.connect(f"{DEFAULT_DB.resolve().as_uri()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        initialized = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='collection_runs'"
        ).fetchone()
        if not initialized:
            st.info("Chưa khởi tạo bảng theo dõi. Chạy `python -m wardprice collection-init`.")
            return
        from wardprice.collectors.storage import monitoring_summary

        summary = monitoring_summary(db)
    except sqlite3.Error as exc:
        st.error(f"Không đọc được trạng thái thu thập: {exc}")
        return
    finally:
        db.close()

    totals = summary["daily_totals"]
    columns = st.columns(6)
    columns[0].metric("Lượt chạy hôm nay", len(summary["runs_today"]))
    columns[1].metric(
        "Địa bàn đã xử lý", f"{summary['processed_target_count_today']} / {summary['target_count']}"
    )
    columns[2].metric("Ứng viên hôm nay", totals["candidates_found"])
    columns[3].metric("Nguồn đã xác minh", totals["source_verified"])
    columns[4].metric("Cách ly / loại", summary["rejected_today"])
    columns[5].metric("Lỗi", totals["errors"])
    st.caption(
        f"Còn {summary['unprocessed_target_count_today']} địa bàn chưa có lượt thử hôm nay · "
        f"{totals['requests_made']} request · {summary['candidate_count']} candidate đã lưu · "
        f"{summary['verified_production_listing_count']} listing trong kho chuẩn"
    )

    readiness = summary["source_readiness"]
    if not readiness["ready_sources"]:
        st.warning(
            "Chưa có nguồn được phê duyệt và bật. Pipeline hiện chỉ có thể chạy dry-run; "
            "không có request web nào được gửi."
        )
    sources = []
    reasons = {item["source_id"]: item["reasons"] for item in readiness["blocked_sources"]}
    for source in summary["sources"]:
        sources.append({
            "Nguồn": source["display_name"],
            "Quyền truy cập": source["policy_status"],
            "Đang bật": source["enabled"],
            "Robots": source["robots_status"],
            "Chặn bởi": ", ".join(reasons.get(source["source_id"], [])) or "Sẵn sàng",
            "Cooldown đến": source.get("cooldown_until") or "—",
        })
    if sources:
        import pandas as pd

        st.markdown("#### Nguồn và trạng thái quyền truy cập")
        st.dataframe(pd.DataFrame(sources), hide_index=True, use_container_width=True)

    st.markdown("#### Candidate theo trạng thái bằng chứng")
    evidence = summary["candidate_evidence_counts"]
    if evidence:
        import pandas as pd

        st.dataframe(pd.DataFrame(evidence), hide_index=True, use_container_width=True)
    else:
        st.info("Chưa có candidate nào được thu thập.")

    if summary["recent_rejections"]:
        st.markdown("#### Các bản ghi bị loại gần đây")
        import pandas as pd

        st.dataframe(pd.DataFrame(summary["recent_rejections"]), hide_index=True, use_container_width=True)

    st.markdown("#### Lần thử theo địa bàn hôm nay")
    attempts = summary["target_attempts_today"]
    if attempts:
        import pandas as pd

        st.dataframe(pd.DataFrame(attempts), hide_index=True, use_container_width=True)
    else:
        st.info("Hôm nay chưa có request thu thập nào được ghi nhận.")

    st.markdown("#### Lịch sử lượt chạy")
    if summary["recent_runs"]:
        import pandas as pd

        st.dataframe(pd.DataFrame(summary["recent_runs"]), hide_index=True, use_container_width=True)
    else:
        st.info("Chưa có lịch sử chạy.")
    st.caption(
        f"Cập nhật candidate gần nhất: {summary['last_candidate_seen_at'] or 'chưa có'} · "
        "Task Scheduler chưa được kích hoạt bởi pipeline này."
    )


def _show_ingestion_pilot_monitoring(st):
    """Read-only operational summary for source-agnostic file/feed ingestion."""
    st.subheader("Pilot nhập dữ liệu đa nguồn")
    st.caption(
        "Đọc từ state/ward_prices.ingestion_pilot.sqlite3. Pilot tách khỏi production, "
        "demo và kho lịch sử; mục này không gọi nguồn hoặc ghi database."
    )
    from wardprice.ingestion_pilot import monitoring_summary

    summary = monitoring_summary(INGESTION_PILOT_DB)
    if summary["status"] == "NOT_INITIALIZED":
        st.info("Pilot chưa khởi tạo. Chạy `python -m wardprice.ingestion_pilot init`.")
        return
    totals = summary["daily_totals"]
    columns = st.columns(5)
    columns[0].metric("Mục tiêu kế hoạch/ngày", summary["daily_goal"])
    columns[1].metric("Mới đăng ≤ 24 giờ", totals["newly_posted"])
    columns[2].metric("Mới phát hiện", totals["newly_discovered"])
    columns[3].metric("Đã xác minh", summary["verified_count"])
    columns[4].metric("Phủ Top 50", f"{summary['covered_targets']} / {summary['target_count']}")
    st.caption(
        f"{summary['candidate_count']} candidate · {summary['stats_eligible_count']} đủ điều kiện thống kê · "
        f"{totals['quarantined']} dòng cách ly hôm nay · Task Scheduler: chưa kích hoạt."
    )
    if not any(source["health"] == "READY" for source in summary["source_health"]):
        st.warning(
            "Chưa có nguồn nào vượt cổng quyền lưu trữ. Import live bị chặn; "
            "có thể dùng preview offline để kiểm tra file mà không lưu dữ liệu."
        )
    if summary["source_health"]:
        import pandas as pd

        st.markdown("#### Quyền nguồn và trạng thái")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Nguồn": row["source_name"],
                        "Loại": row["source_type"],
                        "Quyền": row["permission_status"],
                        "Đang bật": row["enabled"],
                        "Trạng thái": row["health"],
                    }
                    for row in summary["source_health"]
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
    if summary["recent_runs"]:
        st.markdown("#### Lượt nhập gần đây")
        import pandas as pd

        st.dataframe(
            pd.DataFrame(summary["recent_runs"]), hide_index=True, use_container_width=True
        )
    else:
        st.info("Chưa có lượt nhập file nào. Dữ liệu lịch sử TiniX không nằm trong pipeline này.")


def main():
    import streamlit as st

    settings = Settings.from_env()
    global DEFAULT_DB, DEFAULT_OUTPUT
    DEFAULT_DB = settings.database_path
    DEFAULT_OUTPUT = settings.output_path

    admin_enabled = os.getenv("WARDPRICE_ADMIN_VIEW", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    st.set_page_config(
        page_title="WardPriceDaily · Sổ tay giá",
        page_icon="₫",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _render_styles(st)
    if settings.demo_mode:
        DEFAULT_DB = DEMO_DB
        _render_demo_app(st)
        return
    view = _render_app_header(st, admin_enabled)

    if view == "Tra cứu giá":
        _show_national_lookup(st)
        st.markdown(
            '<div class="app-footer">Giá rao được tính từ listing có nguồn đã xác minh. '
            "Dữ liệu chưa đủ căn cứ sẽ được hiển thị là chưa có giá.</div>",
            unsafe_allow_html=True,
        )
        return

    data = _snapshot(settings)
    st.markdown(
        '<div class="eyebrow">KHU VỰC QUẢN TRỊ</div>',
        unsafe_allow_html=True,
    )
    st.title("Theo dõi sổ tay giá")
    st.caption("Quản lý độ phủ, hoạt động thu thập, chất lượng listing và báo cáo.")
    overview, coverage, run, webpilot, collection, listings, outputs = st.tabs(
        [
            "Tổng quan",
            "Độ phủ",
            "Pipeline",
            "Gemini Web pilot",
            "Thu thập web",
            "Tin rao & thống kê",
            "Xuất dữ liệu",
        ]
    )
    with overview:
        _show_overview(st, settings, data)
    with coverage:
        _show_national_coverage(st)
    with run:
        _show_run_tab(st, settings, data)
    with webpilot:
        _render_webpilot_tab(st)
    with collection:
        _show_ingestion_pilot_monitoring(st)
        st.divider()
        _show_collection_monitoring(st)
    with listings:
        _show_data_tab(st, data)
    with outputs:
        _show_outputs_tab(st, settings)


if __name__ == "__main__":
    main()
