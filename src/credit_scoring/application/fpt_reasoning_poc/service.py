"""Application orchestration; research cases and experiment outputs stay out."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from credit_scoring.reasoning.pipeline import FPTPipelineResult, run_fpt_pipeline


def process_upload(
    input_path: str | Path,
    *,
    sheet: str | None = None,
    mapping_path: str | Path | None = None,
    processed_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    explanation_responder: Callable[..., Any] | None = None,
    model: str | None = None,
) -> FPTPipelineResult:
    """Process one uploaded raw file through the shared application pipeline."""

    return run_fpt_pipeline(
        input_path,
        sheet=sheet,
        mapping_path=mapping_path,
        processed_dir=processed_dir,
        output_dir=output_dir,
        explanation_responder=explanation_responder,
        model=model,
    )
