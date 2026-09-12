from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import validate

from .common import CONFIG_DIR, OUTPUT_DIR, PROMPT_DIR, TEST_DIR, read_jsonl, write_jsonl
from .rule_engine import evaluate_profile, load_rules

RESPONSE_CSV_FIELDS = [
    "timestamp",
    "case_id",
    "repeat_index",
    "model",
    "rule_engine_decision",
    "expected_rule_result",
    "expected_recommendation",
    "expected_conflict",
    "ai_rule_result",
    "ai_financial_assessment",
    "ai_conflict_detected",
    "ai_recommendation",
    "ai_confidence",
    "ai_reason",
    "ai_supporting_evidence",
    "ai_risk_evidence",
    "ai_missing_data",
    "response_json",
    "error",
]


def _json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False) if value is not None else ""


def flatten_response_record(record: dict[str, Any]) -> dict[str, Any]:
    """Flatten one JSONL record into a human-readable spreadsheet row."""

    response = record.get("response") or {}
    rule_result = record.get("rule_engine_result") or {}
    return {
        "timestamp": record.get("timestamp", ""),
        "case_id": record.get("case_id", ""),
        "repeat_index": record.get("repeat_index", ""),
        "model": record.get("model", ""),
        "rule_engine_decision": rule_result.get("decision", ""),
        "expected_rule_result": record.get("expected_rule_result", ""),
        "expected_recommendation": record.get("expected_recommendation", ""),
        "expected_conflict": record.get("expected_conflict", ""),
        "ai_rule_result": response.get("rule_result", ""),
        "ai_financial_assessment": response.get("financial_assessment", ""),
        "ai_conflict_detected": response.get("conflict_detected", ""),
        "ai_recommendation": response.get("recommendation", ""),
        "ai_confidence": response.get("confidence", ""),
        "ai_reason": response.get("reason", ""),
        "ai_supporting_evidence": _json_cell(response.get("supporting_evidence")),
        "ai_risk_evidence": _json_cell(response.get("risk_evidence")),
        "ai_missing_data": _json_cell(response.get("missing_data")),
        "response_json": _json_cell(record.get("response")),
        "error": record.get("error") or "",
    }


def write_response_csv(path: Path, records: list[dict[str, Any]]) -> None:
    """Write one readable CSV row per AI response/repeat."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESPONSE_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(flatten_response_record(record) for record in records)


def call_openrouter(
    model: str,
    instructions: str,
    payload: dict[str, Any],
    schema: dict[str, Any],
) -> dict[str, Any]:
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise RuntimeError("Thiếu OPENROUTER_API_KEY. Hãy đặt key mới trong biến môi trường.")
    from openai import OpenAI

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
        default_headers={"X-OpenRouter-Title": "FPT Credit Reasoning Research"},
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "credit_reasoning",
                "strict": True,
                "schema": schema,
            },
        },
        extra_body={"provider": {"require_parameters": True}},
    )
    content = response.choices[0].message.content
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("OpenRouter trả về nội dung rỗng.")
    parsed = json.loads(content)
    validate(instance=parsed, schema=schema)
    return parsed


def run(
    input_path: Path,
    output_path: Path,
    model: str,
    repeats: int,
    csv_output_path: Path | None = None,
) -> list[dict[str, Any]]:
    cases = read_jsonl(input_path)
    rules = load_rules()
    schema = json.loads((CONFIG_DIR / "response_schema.json").read_text(encoding="utf-8"))
    instructions = (PROMPT_DIR / "credit_reasoning.md").read_text(encoding="utf-8")
    records: list[dict[str, Any]] = []
    for case in cases:
        rule_result = evaluate_profile(case["profile"], rules)
        payload = {
            "profile": case["profile"],
            "rule_engine_result": rule_result,
            "test_expectations": {
                "expected_missing_fields": case.get("expected_missing_fields", []),
            },
        }
        for repeat_index in range(repeats):
            record: dict[str, Any] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "case_id": case["case_id"],
                "repeat_index": repeat_index,
                "model": model,
                "rule_engine_result": rule_result,
                "expected_rule_result": case["expected_rule_result"],
                "expected_recommendation": case["expected_recommendation"],
                "expected_conflict": case["expected_conflict"],
            }
            try:
                record["response"] = call_openrouter(model, instructions, payload, schema)
                record["error"] = None
            except Exception as exc:  # noqa: BLE001 - keep batch results when one API call fails
                record["response"] = None
                record["error"] = f"{type(exc).__name__}: {exc}"
            records.append(record)
            write_jsonl(output_path, records)
            if csv_output_path is not None:
                write_response_csv(csv_output_path, records)
            print(f"{case['case_id']} repeat={repeat_index}: {'OK' if record['error'] is None else record['error']}")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Gọi AI để giải thích các test case")
    parser.add_argument("--input", type=Path, default=TEST_DIR / "test_cases.jsonl")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "experiment_results.jsonl")
    parser.add_argument("--csv-output", type=Path, default=None)
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
    )
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    if args.repeats < 1:
        raise SystemExit("--repeats phải >= 1")
    csv_output = args.csv_output or args.output.with_suffix(".csv")
    records = run(args.input, args.output, args.model, args.repeats, csv_output)
    print(f"Đã ghi bảng response: {csv_output} ({len(records)} dòng)")


if __name__ == "__main__":
    main()
