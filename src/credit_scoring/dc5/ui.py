"""Local Streamlit UI for running and inspecting the DC5 pipeline."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from credit_scoring.dc5.config import ModelConfig, PipelineConfig, ValidationConfig
from credit_scoring.dc5.pipeline import PipelineRun, run_pipeline, smoke_check
from credit_scoring.dc5.simulation import simulate_profile


def _render_simulation(st: object) -> None:
    st.header("Vòng 1 — Nhập hồ sơ khách hàng")
    st.warning(
        "Giai đoạn 1: chỉ tạo chỉ số minh họa để xem tác động của thông tin nhập vào. "
        "Chưa phải CIC score, credit score hoặc quyết định cho vay."
    )
    with st.form("profile_simulation"):
        left, right = st.columns(2)
        with left:
            age = st.number_input("Tuổi", min_value=18, max_value=100, value=35, step=1)
            income = st.number_input("Thu nhập (triệu VNĐ/tháng)", min_value=0.0, value=15.0, step=1.0)
            occupation = st.selectbox("Nghề nghiệp (survey)", [
                "Nhân viên văn phòng", "Kinh doanh tự do", "Công chức/viên chức",
                "Lao động kỹ thuật", "Sinh viên", "Khác",
            ])
            employment_years = st.number_input("Thâm niên làm việc (năm)", min_value=0.0, value=3.0, step=0.5)
        with right:
            household = st.selectbox("Loại hình nhà ở", ["Nhà thường", "Chung cư", "Nhà trọ", "Khác"])
            dependents = st.number_input("Số người phụ thuộc", min_value=0, max_value=20, value=1, step=1)
            service_count = st.number_input("Số dịch vụ đang sử dụng", min_value=0, max_value=10, value=2, step=1)
            cic_input = st.number_input("CIC score (tùy chọn, chưa dùng trong model)", min_value=0, max_value=900, value=0, step=1)
        st.subheader("Tài liệu xác minh (tùy chọn)")
        st.caption("Demo chỉ nhận file trong phiên làm việc; chưa OCR, chưa lưu và không gửi ra ngoài.")
        cccd_file = st.file_uploader("CCCD/giấy tờ định danh", type=["png", "jpg", "jpeg", "pdf"])
        income_file = st.file_uploader("Tài liệu thu nhập (nếu có)", type=["png", "jpg", "jpeg", "pdf"])
        submitted = st.form_submit_button("Xác nhận hồ sơ vòng 1", type="primary")
    if not submitted:
        return
    result = simulate_profile(
        age=int(age), income_million_vnd=float(income), occupation=occupation,
        employment_years=float(employment_years), household_type=household,
        dependents=int(dependents), service_count=int(service_count),
        cic_score=int(cic_input) if cic_input else None,
    )
    st.success("Đã hoàn tất vòng 1: hồ sơ đã được tiếp nhận.")
    st.metric("Demo profile index", result["demo_index"])
    st.caption(result["note"])
    st.write({
        "occupation": occupation,
        "household_type": household,
        "documents_received": sum(file is not None for file in (cccd_file, income_file)),
    })
    if result["cic_score"] is None:
        st.info("Vòng 2 — CIC đang để trạng thái CHƯA TÍNH. Khi có model CIC được phê duyệt, trường này sẽ được nối vào bước dự đoán riêng.")
    else:
        st.info(f"Đã nhập CIC {result['cic_score']}, nhưng hiện tại CIC chưa được dùng để tính demo index.")
    st.subheader("Đóng góp minh họa của từng nhóm input")
    st.dataframe(
        pd.DataFrame(
            [{"feature_group": key, "normalized_value": value} for key, value in result["components"].items()]
        ),
        use_container_width=True,
        hide_index=True,
    )


def _render_run(st: object, run: PipelineRun) -> None:
    st.success("Đã tải kết quả từ cache." if run.cached else "Pipeline đã chạy thành công.")
    st.caption(f"Artifact: {run.run_dir}")
    st.subheader("So sánh mô hình")
    st.dataframe(run.metrics, use_container_width=True, hide_index=True)
    comparison = run.run_dir / "plots" / "model_comparison.png"
    if comparison.is_file():
        st.image(str(comparison), caption="OOF ROC-AUC và PR-AUC")
    importance_path = run.run_dir / "feature_importance.csv"
    if importance_path.is_file():
        importance = pd.read_csv(importance_path)
        settings = importance[["setting", "model"]].drop_duplicates()
        labels = [f"{row.setting} / {row.model}" for row in settings.itertuples()]
        selected = st.selectbox("Xem feature importance", labels)
        setting, model = selected.split(" / ", maxsplit=1)
        selected_importance = importance.loc[
            importance["setting"].eq(setting) & importance["model"].eq(model)
        ].head(20)
        st.dataframe(selected_importance, use_container_width=True, hide_index=True)
    st.download_button(
        "Tải report.html",
        data=run.report_path.read_bytes(),
        file_name="dc5_report.html",
        mime="text/html",
    )


def render_app() -> None:
    """Render the interactive UI; all analysis remains in the pipeline modules."""

    try:
        import streamlit as st
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError('DC5 UI requires: python -m pip install -e ".[dc5,ui]"') from exc

    st.set_page_config(page_title="DC5 Customer Analysis", page_icon="📊", layout="wide")
    st.title("DC5 Customer Analysis")
    st.caption("Research candidate — target Telco monetary, không phải credit-risk target.")
    _render_simulation(st)
    st.divider()
    st.header("Pipeline phân tích DC5")
    with st.sidebar:
        st.header("Cấu hình")
        data_path = Path(
            st.text_input("Prepared Parquet", "data_extracted/model_df_extracted.parquet")
        )
        output_dir = Path(st.text_input("Artifact directory", "artifacts/dc5_customer_analysis"))
        mode = st.selectbox("Chế độ", ("quick", "full", "report-only"))
        backend = st.selectbox("Model backend", ("catboost", "logistic"))
        include_city = st.checkbox("So sánh có/không City", value=True)
        clustering_enabled = st.checkbox("Clustering trong Full mode", value=True)
        force = st.checkbox("Chạy lại, bỏ qua cache", value=False)
        run_clicked = st.button("Chạy pipeline", type="primary", use_container_width=True)
        latest_clicked = st.button("Xem kết quả gần nhất", use_container_width=True)

    st.info(
        "Quick chạy M0/M1/M4 với tối đa 3 folds. Full chạy M0-M4 với 5 folds. "
        "Report-only mở artifact gần nhất mà không train lại."
    )
    if not run_clicked and not latest_clicked:
        if (output_dir / "latest.json").is_file():
            run = run_pipeline(
                config=PipelineConfig(
                    data_path=data_path,
                    output_dir=output_dir,
                    mode="report-only",
                )
            )
            _render_run(st, run)
        return
    if latest_clicked:
        try:
            run = run_pipeline(
                config=PipelineConfig(
                    data_path=data_path,
                    output_dir=output_dir,
                    mode="report-only",
                )
            )
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            st.error(str(exc))
            return
        _render_run(st, run)
        return
    smoke_check()
    config = PipelineConfig(
        data_path=data_path,
        output_dir=output_dir,
        mode=mode,
        include_city_comparison=include_city,
        clustering_enabled=clustering_enabled,
        validation=ValidationConfig(n_splits=5, random_state=42),
        model=ModelConfig(backend=backend),
    )
    try:
        with st.spinner("Đang xử lý dữ liệu và huấn luyện mô hình..."):
            run = run_pipeline(config=config, force=force)
    except (FileNotFoundError, ImportError, OSError, TypeError, ValueError) as exc:
        st.error(str(exc))
        return
    _render_run(st, run)


def cli_main() -> None:
    """Launch this module through the Streamlit command-line runner."""

    try:
        from streamlit.web import cli as stcli
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError('DC5 UI requires: python -m pip install -e ".[dc5,ui]"') from exc
    sys.argv = ["streamlit", "run", str(Path(__file__).resolve())]
    raise SystemExit(stcli.main())


if __name__ == "__main__":  # pragma: no cover
    render_app()
