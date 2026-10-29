"""Command line: `claims-extractor run|export`."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Callable, Sequence

from .domains import available_domains, get_domain
from .export import export_csv, export_jsonl
from .extract import Extractor
from .llm import LLMClient, OpenAICompatibleClient
from .pipeline import run_pipeline
from .store import ClaimStore

DEFAULT_MODEL = "gpt-4o-mini"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="claims-extractor", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default="claims.db", help="SQLite store (default: claims.db)")
    common.add_argument("--domain", default="real_estate", choices=available_domains())

    run = sub.add_parser("run", parents=[common], help="extract claims from a phase-1 file")
    run.add_argument("--input", required=True, help="llm_answers file (.jsonl or .json)")
    run.add_argument("--model", default=os.environ.get("CLAIMS_MODEL", DEFAULT_MODEL))
    run.add_argument("--force", action="store_true", help="re-extract answers already stored")
    run.add_argument("--limit", type=int, help="max answers sent to the LLM in this run")

    export = sub.add_parser("export", parents=[common], help="dump claims to CSV or JSONL")
    export.add_argument("--format", choices=["csv", "jsonl"], default="csv")
    export.add_argument("--out", required=True)
    return parser


def main(
    argv: Sequence[str] | None = None,
    llm_factory: Callable[[str], LLMClient] = OpenAICompatibleClient,
) -> int:
    args = _build_parser().parse_args(argv)
    domain = get_domain(args.domain)

    with ClaimStore(args.db) as store:
        if args.command == "export":
            writer = export_csv if args.format == "csv" else export_jsonl
            print(f"Exported {writer(store, domain, args.out)} claims to {args.out}")
            return 0

        extractor = Extractor(llm_factory(args.model), domain)
        summary = run_pipeline(args.input, store, extractor, force=args.force, limit=args.limit)

    print(
        f"processed={summary.processed} skipped={summary.skipped} ok={summary.ok} "
        f"empty={summary.empty} failed={summary.failed} claims={summary.claims} "
        f"rejected={summary.rejected}"
    )
    for problem in summary.invalid_inputs:
        print(f"invalid input: {problem}", file=sys.stderr)
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
