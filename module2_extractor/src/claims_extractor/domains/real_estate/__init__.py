"""Real-estate price-claim domain."""

from __future__ import annotations

import json
from pathlib import Path

from ...domain import Domain
from .processor import process_claim
from .schema import CSV_COLUMNS, ExtractionResult
from .sources import declares_no_result, strip_sources

# Bump when verification code (processor.py / sources.py) changes in a way that alters results.
VERSION = "2"
_PROMPT_FILE = Path(__file__).with_name("prompt.md")


def load_system_prompt() -> str:
    schema = json.dumps(ExtractionResult.model_json_schema(), ensure_ascii=False, indent=2)
    return _PROMPT_FILE.read_text(encoding="utf-8").replace("{schema}", schema)


def build_domain() -> Domain:
    return Domain(
        name="real_estate",
        system_prompt=load_system_prompt(),
        process_claim=process_claim,
        csv_columns=list(CSV_COLUMNS),
        version=VERSION,
        precheck=declares_no_result,
        preprocess=strip_sources,
    )
