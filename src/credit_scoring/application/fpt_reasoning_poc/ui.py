"""Streamlit UI for the single-upload FPT reasoning application."""

from __future__ import annotations

import tempfile
import json
from pathlib import Path

import pandas as pd

from credit_scoring.application.fpt_reasoning_poc.service import process_upload
from credit_scoring.reasoning.ingestion import inspect_input
from credit_scoring.reasoning.mapping import load_feature_mapping
from credit_scoring.research.fpt_reasoning_poc.experiments import (
    ResearchExperimentConfig,
    run_research_experiment,
    write_experiment_results,
)


def _render_pipeline(st: object, result: object) -> None:
    st.subheader("Upload / Inspect")
    inspection = result.inspection.to_dict()
    left, middle, right = st.columns(3)
    left.metric("Số dòng", inspection["row_count"])
    middle.metric("Số cột", inspection["column_count"])
    right.metric("Số user", len(inspection["detected_users"]))
    st.json(inspection)

    tabs = st.tabs(
        [
            "Raw → Important Mapping",
            "Customer Profile",
            "Validation",
            "Rule Result",
            "AI Explanation",
            "Research",
        ]
    )
    with tabs[0]:
        mapping_path = result.artifact_paths.get("mapping_report")
        rows = (
            json.loads(mapping_path.read_text(encoding="utf-8"))
            if mapping_path is not None and mapping_path.is_file()
            else _mapping_rows(result)
        )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    with tabs[1]:
        selected = st.selectbox("user_id", [profile["user_id"] for profile in result.profiles])
        profile = next(item for item in result.profiles if item["user_id"] == selected)
        st.json(profile)
    with tabs[2]:
        summary = result.validation_report["summary"]
        st.write(summary)
        st.json(
            {
                "errors": result.validation_report["errors"],
                "warnings": result.validation_report["warnings"],
                "missing_columns": result.validation_report["missing_columns"],
            }
        )
    with tabs[3]:
        st.dataframe(pd.DataFrame(result.rule_results), use_container_width=True, hide_index=True)
        st.caption("Official rule decision là output deterministic; AI không được override.")
    with tabs[4]:
        if not result.explanations:
            st.info("Chưa gọi model. Có thể nối responder dùng secret từ environment variable.")
        else:
            st.json(result.explanations)
    with tabs[5]:
        _render_research(st, result)


def _mapping_rows(result: object) -> list[dict]:
    rows = []
    for group in (
        "user_id",
        "age",
        "local_context",
        "location",
        "device_usage",
        "payment_history_12m",
        "shopping_installment",
        "orders",
        "healthcare_spending",
        "fpt_education",
    ):
        profile = result.profiles[0][group]
        rows.append(
            {
                "Business field": group,
                "Raw columns used": ", ".join(profile.get("raw_columns", [])),
                "Raw columns missing": ", ".join(profile.get("missing_raw_columns", [])),
                "Transform": profile.get("transform", "identity"),
                "Status": profile.get("status", "available"),
                "Semantic type": profile.get("semantic_type", "identifier"),
                "Source trace": len(profile.get("evidence", [])),
            }
        )
    return rows


def _render_research(st: object, result: object) -> None:
    st.caption("Research candidate: runs are evaluation artifacts, not application decisions.")
    labels = {
        "current": "A — current",
        "current_healthcare": "B — current + healthcare",
        "current_fpt_education": "C — current + FPT education",
        "current_both": "D — current + healthcare + FPT education",
    }
    selected_labels = st.multiselect(
        "Feature configurations",
        list(labels.values()),
        default=list(labels.values()),
    )
    selected = tuple(key for key, label in labels.items() if label in selected_labels)
    repeat_count = int(st.number_input("Repeat count", min_value=1, value=1, step=1))
    model = st.text_input("Model label", value="not_configured")
    if not st.button("Prepare research runs"):
        return
    config = ResearchExperimentConfig(
        repeat_count=repeat_count,
        model=model,
        case_ids=tuple(profile["user_id"] for profile in result.profiles),
        configurations=selected or ("current",),
    )
    runs = run_research_experiment(result.profiles, config=config)
    write_experiment_results(
        runs,
        jsonl_path=Path("outputs/research/fpt_reasoning_poc/experiment_results.jsonl"),
        csv_path=Path("outputs/research/fpt_reasoning_poc/experiment_results.csv"),
    )
    st.success(f"Đã chuẩn bị {len(runs)} runs; chưa gọi model vì chưa cấu hình responder.")
    st.dataframe(pd.DataFrame(runs), use_container_width=True, hide_index=True)


def render_app() -> None:
    try:
        import streamlit as st
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError('FPT reasoning UI requires: python -m pip install -e ".[fpt,ui]"') from exc
    st.set_page_config(page_title="FPT Credit Reasoning PoC", page_icon="🧭", layout="wide")
    st.title("FPT Credit Reasoning PoC")
    st.warning(
        "Research PoC: DATA → RULES decide → AI explains. Không phải hệ thống xét duyệt tín dụng thật."
    )
    uploaded = st.file_uploader("Upload raw .xlsx hoặc .csv", type=["xlsx", "csv"])
    if uploaded is None:
        st.info("Chọn workbook để bắt đầu. Excel sẽ ưu tiên sheet Synthetic_Customers.")
        return
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded.name).suffix) as handle:
        handle.write(uploaded.getbuffer())
        path = Path(handle.name)
    mapping = load_feature_mapping()
    inspection = inspect_input(path, mapping=mapping)
    selected_sheet = inspection.selected_sheet
    if inspection.sheet_names:
        selected_sheet = st.selectbox("Selected sheet", inspection.sheet_names, index=inspection.sheet_names.index(selected_sheet))
    if st.button("Run validation → profile → rule", type="primary"):
        try:
            result = process_upload(path, sheet=selected_sheet, mapping_path=None)
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            st.error(str(exc))
            return
        st.session_state["fpt_reasoning_result"] = result
    result = st.session_state.get("fpt_reasoning_result")
    if result is not None:
        _render_pipeline(st, result)


def cli_main() -> None:
    try:
        from streamlit.web import cli as stcli
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError('FPT reasoning UI requires: python -m pip install -e ".[fpt,ui]"') from exc
    import sys

    sys.argv = ["streamlit", "run", str(Path(__file__).resolve())]
    raise SystemExit(stcli.main())


if __name__ == "__main__":  # pragma: no cover
    render_app()
