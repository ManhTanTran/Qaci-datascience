"""Admin/research Streamlit UI for DC5 data, training and reports."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from credit_scoring.dc5.config import ModelConfig, PipelineConfig, ValidationConfig
from credit_scoring.dc5.pipeline import PipelineRun, run_pipeline, smoke_check


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
        selected_importance = importance.loc[importance["setting"].eq(setting) & importance["model"].eq(model)].head(20)
        st.dataframe(selected_importance, use_container_width=True, hide_index=True)
    st.download_button("Tải report.html", data=run.report_path.read_bytes(), file_name="dc5_report.html", mime="text/html")


def render_app() -> None:
    import streamlit as st
    st.set_page_config(page_title="DC5 Admin", page_icon="🛠️", layout="wide")
    st.title("DC5 Admin / Research UI")
    st.caption("Dành cho data team: chạy pipeline, training classification và xem báo cáo.")
    st.warning("Không chia sẻ màn hình này cho người dùng cuối.")
    with st.sidebar:
        st.header("Pipeline")
        data_path = Path(st.text_input("Prepared Parquet", "data_extracted/model_df_extracted.parquet"))
        output_dir = Path(st.text_input("Artifact directory", "artifacts/dc5_customer_analysis"))
        mode = st.selectbox("Chế độ", ("quick", "full", "report-only"))
        backend = st.selectbox("Model backend", ("catboost", "logistic"))
        include_city = st.checkbox("So sánh có/không City", value=True)
        clustering_enabled = st.checkbox("Clustering trong Full mode", value=True)
        force = st.checkbox("Chạy lại, bỏ qua cache", value=False)
        run_clicked = st.button("Chạy pipeline", type="primary", use_container_width=True)
        latest_clicked = st.button("Xem kết quả gần nhất", use_container_width=True)
    if not run_clicked and not latest_clicked:
        if (output_dir / "latest.json").is_file():
            _render_run(st, run_pipeline(config=PipelineConfig(data_path=data_path, output_dir=output_dir, mode="report-only")))
        return
    try:
        if latest_clicked:
            run = run_pipeline(config=PipelineConfig(data_path=data_path, output_dir=output_dir, mode="report-only"))
        else:
            smoke_check()
            config = PipelineConfig(data_path=data_path, output_dir=output_dir, mode=mode, include_city_comparison=include_city, clustering_enabled=clustering_enabled, validation=ValidationConfig(n_splits=5, random_state=42), model=ModelConfig(backend=backend))
            with st.spinner("Đang xử lý dữ liệu và huấn luyện mô hình..."):
                run = run_pipeline(config=config, force=force)
    except (FileNotFoundError, ImportError, OSError, TypeError, ValueError) as exc:
        st.error(str(exc))
        return
    _render_run(st, run)


def cli_main() -> None:
    from streamlit.web import cli as stcli
    sys.argv = ["streamlit", "run", str(Path(__file__).resolve())]
    raise SystemExit(stcli.main())


if __name__ == "__main__":
    render_app()
