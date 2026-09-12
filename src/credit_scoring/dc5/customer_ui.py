"""Customer-facing Streamlit UI for profile intake and phase-one simulation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from credit_scoring.dc5.lead import LEAD_SCHEMA_VERSION, parse_lead_json
from credit_scoring.dc5.simulation import simulate_profile


def _show_result(st: object, profile: dict[str, object], *, source: str) -> None:
    result = simulate_profile(**profile)
    st.success(f"Đã tiếp nhận hồ sơ ({source}).")
    st.metric("Demo profile index", result["demo_index"])
    st.caption(result["note"])
    st.write({"source": source, "documents_received": 0})
    st.info("Vòng 2 — CIC: CHƯA TÍNH. Model CIC sẽ được nối vào đây sau khi có dữ liệu train.")
    st.subheader("Đóng góp minh họa của input")
    st.dataframe(
        pd.DataFrame(
            [{"feature_group": key, "normalized_value": value} for key, value in result["components"].items()]
        ),
        use_container_width=True,
        hide_index=True,
    )


def render_app() -> None:
    import streamlit as st
    st.set_page_config(page_title="Customer Profile", page_icon="👤", layout="centered")
    st.title("Customer Profile")
    st.caption("Nhập hồ sơ hoặc upload lead JSON để xem kết quả simulation.")
    st.info("CIC score hiện chưa được tính vì chưa có model CIC được train và phê duyệt.")

    st.subheader("Upload lead JSON")
    st.caption(
        f"Dùng một object JSON theo schema {LEAD_SCHEMA_VERSION}; file chỉ được đọc trong phiên demo, không lưu hoặc gửi ra ngoài."
    )
    sample_lead = {
        "schema_version": LEAD_SCHEMA_VERSION,
        "age": 35,
        "income_million_vnd": 15,
        "occupation": "Nhân viên văn phòng",
        "employment_years": 3,
        "household_type": "Chung cư",
        "dependents": 1,
        "service_count": 2,
        "cic_score": None,
    }
    st.download_button(
        "Tải JSON mẫu",
        data=json.dumps(sample_lead, ensure_ascii=False, indent=2),
        file_name="dc5_lead_example.json",
        mime="application/json",
    )
    lead_file = st.file_uploader("Chọn file lead (.json)", type=["json"], key="lead_json")
    if lead_file is not None:
        try:
            lead_profile = parse_lead_json(lead_file.getvalue())
        except (TypeError, ValueError) as exc:
            st.error(str(exc))
        else:
            st.success("JSON hợp lệ. Hãy kiểm tra preview trước khi xác nhận.")
            st.json(lead_profile)
            if st.button("Xác nhận lead JSON", type="primary"):
                _show_result(st, lead_profile, source="lead JSON")

    st.divider()
    st.subheader("Hoặc nhập thủ công")
    with st.form("customer_profile"):
        age = st.number_input("Tuổi", min_value=18, max_value=100, value=35, step=1)
        income = st.number_input("Thu nhập (triệu VNĐ/tháng)", min_value=0.0, value=15.0, step=1.0)
        occupation = st.selectbox("Nghề nghiệp", ["Nhân viên văn phòng", "Kinh doanh tự do", "Công chức/viên chức", "Lao động kỹ thuật", "Sinh viên", "Khác"])
        employment_years = st.number_input("Thâm niên làm việc (năm)", min_value=0.0, value=3.0, step=0.5)
        household = st.selectbox("Loại hình nhà ở", ["Nhà thường", "Chung cư", "Nhà trọ", "Khác"])
        dependents = st.number_input("Số người phụ thuộc", min_value=0, max_value=20, value=1, step=1)
        service_count = st.number_input("Số dịch vụ đang sử dụng", min_value=0, max_value=10, value=2, step=1)
        cic_input = st.number_input("CIC score (tùy chọn)", min_value=0, max_value=900, value=0, step=1)
        st.subheader("Tài liệu xác minh (tùy chọn)")
        st.caption("Demo không OCR, không lưu và không gửi file ra ngoài.")
        cccd_file = st.file_uploader("CCCD/giấy tờ định danh", type=["png", "jpg", "jpeg", "pdf"])
        income_file = st.file_uploader("Tài liệu thu nhập", type=["png", "jpg", "jpeg", "pdf"])
        submitted = st.form_submit_button("Xác nhận hồ sơ vòng 1", type="primary")
    if not submitted:
        return
    profile = {"age": int(age), "income_million_vnd": float(income), "occupation": occupation,
               "employment_years": float(employment_years), "household_type": household,
               "dependents": int(dependents), "service_count": int(service_count),
               "cic_score": int(cic_input) if cic_input else None}
    result = simulate_profile(**profile)
    st.success("Đã hoàn tất vòng 1: hồ sơ đã được tiếp nhận.")
    st.metric("Demo profile index", result["demo_index"])
    st.caption(result["note"])
    st.write({"source": "nhập thủ công", "documents_received": sum(file is not None for file in (cccd_file, income_file))})
    if result["cic_score"] is None:
        st.info("Vòng 2 — CIC: CHƯA TÍNH. Model CIC sẽ được nối vào đây sau khi có dữ liệu train.")
    else:
        st.info(f"Đã nhập CIC {result['cic_score']}; hiện tại chưa dùng để tính điểm.")
    st.subheader("Đóng góp minh họa của input")
    st.dataframe(pd.DataFrame([{"feature_group": key, "normalized_value": value} for key, value in result["components"].items()]), use_container_width=True, hide_index=True)


def cli_main() -> None:
    from streamlit.web import cli as stcli
    sys.argv = ["streamlit", "run", str(Path(__file__).resolve())]
    raise SystemExit(stcli.main())


if __name__ == "__main__":
    render_app()
