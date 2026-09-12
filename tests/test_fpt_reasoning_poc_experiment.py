from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from credit_scoring.research.fpt_reasoning_poc.run_experiment import (
    call_openrouter,
    write_response_csv,
)


class ExperimentRunnerTests(unittest.TestCase):
    def test_structured_output_request_and_response(self) -> None:
        schema = {
            "type": "object",
            "properties": {"result": {"type": "string"}},
            "required": ["result"],
            "additionalProperties": False,
        }
        fake_response = MagicMock()
        fake_response.choices[0].message.content = json.dumps({"result": "OK"})
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = fake_response

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}), patch(
            "openai.OpenAI", return_value=fake_client
        ):
            result = call_openrouter("openai/gpt-4o-mini", "instructions", {"profile": {}}, schema)

        self.assertEqual(result, {"result": "OK"})
        kwargs = fake_client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["response_format"]["type"], "json_schema")
        self.assertTrue(kwargs["response_format"]["json_schema"]["strict"])

    def test_missing_api_key_fails_before_network_call(self) -> None:
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(
            RuntimeError, "OPENROUTER_API_KEY"
        ):
            call_openrouter("openai/gpt-4o-mini", "instructions", {}, {"type": "object"})

    def test_response_csv_keeps_reasoning_fields_and_raw_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "experiment_results.csv"
            write_response_csv(
                output,
                [
                    {
                        "timestamp": "2026-09-10T00:00:00Z",
                        "case_id": "A_OVER23_GOOD",
                        "repeat_index": 0,
                        "model": "openai/gpt-4o-mini",
                        "rule_engine_result": {"decision": "ELIGIBLE"},
                        "expected_rule_result": "ELIGIBLE",
                        "expected_recommendation": "CONSIDER",
                        "expected_conflict": False,
                        "response": {
                            "rule_result": "ELIGIBLE",
                            "financial_assessment": "POSITIVE",
                            "conflict_detected": False,
                            "recommendation": "CONSIDER",
                            "supporting_evidence": ["payment history"],
                            "risk_evidence": [],
                            "missing_data": ["installment history"],
                            "reason": "Rule and financial evidence align.",
                            "confidence": "HIGH",
                        },
                        "error": None,
                    }
                ],
            )
            text = output.read_text(encoding="utf-8-sig")
            self.assertIn("ai_reason", text)
            self.assertIn("Rule and financial evidence align.", text)
            self.assertIn("response_json", text)


if __name__ == "__main__":
    unittest.main()
