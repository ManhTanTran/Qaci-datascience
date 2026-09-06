"""Customer-facing Streamlit UI for profile intake and phase-one simulation."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from credit_scoring.dc5.simulation import simulate_profile


def render_app() -> None:
    import streamlit as st
    st.set_page_config(page_title="Customer Profile", page_icon="👤", layout="centered")
    st.title("Customer Profile")
    st.caption("Nhập hồ sơ để xem kết quả simulation.")
    st.info("CIC score hiện chưa được tính vì chưa có model CIC được train và phê duyệt.")
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
    result = simulate_profile(age=int(age), income_million_vnd=float(income), occupation=occupation, employment_years=float(employment_years), household_type=household, dependents=int(dependents), service_count=int(service_count), cic_score=int(cic_input) if cic_input else None)
    st.success("Đã hoàn tất vòng 1: hồ sơ đã được tiếp nhận.")
    st.metric("Demo profile index", result["demo_index"])
    st.caption(result["note"])
    st.write({"documents_received": sum(file is not None for file in (cccd_file, income_file))})
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
