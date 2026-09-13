"""Structured research runner with environment-only provider credentials."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any

from credit_scoring.research.fpt_reasoning_poc.common import CONFIG_DIR, read_jsonl
from credit_scoring.research.fpt_reasoning_poc.experiments import (
    RESEARCH_CONFIGURATIONS,
    ResearchExperimentConfig,
    run_research_experiment,
)


def call_openrouter(
    model: str,
    instructions: str,
    payload: dict[str, Any],
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Call OpenRouter without ever accepting a key as a function argument/output."""

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("Thiếu OPENROUTER_API_KEY; chỉ đọc secret từ biến môi trường.")
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Cần cài openai để chạy LLM research.") from exc
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={"X-OpenRouter-Title": "FPT Credit Reasoning Research"},
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "fpt_reasoning_explanation",
                "strict": True,
                "schema": schema,
            },
        },
        extra_body={"provider": {"require_parameters": True}},
    )
    content = response.choices[0].message.content
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("OpenRouter trả về nội dung rỗng.")
    result = json.loads(content)
    if not isinstance(result, dict):
        raise TypeError("Structured response phải là JSON object.")
    return result


RESPONSE_CSV_FIELDS = [
    "experiment_id",
    "case_id",
    "run_id",
    "repeat_id",
    "model",
    "configuration",
    "rule_decision",
    "response_status",
    "ai_reason",
    "rule_conflict",
    "response_json",
    "error",
]


def _json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str) if value is not None else ""


def flatten_response_record(record: dict[str, Any]) -> dict[str, Any]:
    response = record.get("response") or {}
    rule_result = record.get("rule_result") or record.get("rule_engine_result") or {}
    return {
        "experiment_id": record.get("experiment_id", ""),
        "case_id": record.get("case_id", ""),
        "run_id": record.get("run_id", ""),
        "repeat_id": record.get("repeat_id", record.get("repeat_index", "")),
        "model": record.get("model", ""),
        "configuration": record.get("configuration", record.get("run_type", "")),
        "rule_decision": rule_result.get("decision", rule_result.get("rule_result", "")),
        "response_status": response.get("status", ""),
        "ai_reason": response.get("explanation", response.get("reason", "")),
        "rule_conflict": response.get("rule_conflict", response.get("conflict_detected", "")),
        "response_json": _json_cell(record.get("raw_response", record.get("response"))),
        "error": record.get("error") or "",
    }


def write_response_csv(path: str | Path, records: list[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESPONSE_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(flatten_response_record(record) for record in records)


def run(
    input_path: str | Path,
    output_path: str | Path,
    *,
    model: str,
    repeats: int,
    configurations: tuple[str, ...] = tuple(RESEARCH_CONFIGURATIONS),
    responder: Any | None = None,
    csv_output_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    cases = read_jsonl(input_path)
    profiles = [case["profile"] for case in cases]
    case_ids = tuple(str(case["case_id"]) for case in cases)
    config = ResearchExperimentConfig(
        experiment_id="fpt_reasoning_poc",
        repeat_count=repeats,
        model=model,
        case_ids=case_ids,
        configurations=configurations,
    )
    if responder is None:
        schema = json.loads((CONFIG_DIR / "response_schema.json").read_text(encoding="utf-8"))
        instructions = (
            "Chỉ giải thích profile và rule_result; không đưa ra quyết định khoản vay "
            "và không biến contextual proxy thành thuộc tính cá nhân."
        )

        def responder(context, model=model):
            return call_openrouter(model, instructions, context, schema)
    results = run_research_experiment(profiles, config=config, responder=responder)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
    if csv_output_path is not None:
        write_response_csv(csv_output_path, results)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Chạy repeated structured research runs.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=os.environ.get("REASONING_LLM_MODEL", "not_configured"))
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--csv-output", type=Path, default=None)
    args = parser.parse_args()
    if args.repeats < 1:
        raise SystemExit("--repeats phải >= 1")
    records = run(
        args.input,
        args.output,
        model=args.model,
        repeats=args.repeats,
        csv_output_path=args.csv_output,
    )
    print(f"Đã ghi {len(records)} research runs.")


if __name__ == "__main__":
    main()
