"""`python -m pipeline <command>` — every command also exists as a button in the UI."""

from __future__ import annotations

import argparse
import json
import sys
import threading
from typing import Sequence

from claims_extractor import stats
from common.config import ConfigError, load_config

from .runner import Runner, WorkerBusy, setup_logging


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m pipeline", description=__doc__)
    p.add_argument("--config", help="đường dẫn config.yaml (mặc định: ./config.yaml)")
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run-once", help="quét file đầu vào + xử lý answer mới, rồi dừng")
    run.add_argument("--limit", type=int, help="chỉ xử lý tối đa N answer (chạy thử rẻ)")
    run.add_argument("--rescan", action="store_true", help="đọc lại file từ đầu (an toàn, không nhân đôi)")

    sub.add_parser("watch", help="chạy liên tục, tự xử lý khi file đầu vào đổi (mode auto)")
    sub.add_parser("status", help="in tình trạng hàng chờ và chất lượng")

    rp = sub.add_parser("reprocess", help="đưa answer đã xử lý quay lại hàng chờ (có chủ đích)")
    rp.add_argument("--status", action="append", choices=["ok", "empty", "failed"])
    rp.add_argument("--answer-id", action="append")
    rp.add_argument("--month", help="target_month, ví dụ 2026-10")
    rp.add_argument("--crawl-run-id")
    rp.add_argument("--stale", action="store_true", help="answer trích bằng prompt/logic cũ")
    rp.add_argument("--run", action="store_true", help="chạy xử lý ngay sau khi xếp hàng")

    ex = sub.add_parser("export", help="xuất claim ra CSV/JSONL")
    ex.add_argument("--format", choices=["csv", "jsonl"], default="csv")
    ex.add_argument("--month")

    ui = sub.add_parser("ui", help="mở UI vận hành + giám sát module 2")
    ui.add_argument("--host")
    ui.add_argument("--port", type=int)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Lỗi cấu hình: {exc}", file=sys.stderr)
        return 2
    setup_logging(config)
    runner = Runner(config)

    if args.command == "run-once":
        try:
            result = runner.run_once("cli", limit=args.limit, rescan=args.rescan)
        except WorkerBusy as busy:
            print(f"Không chạy: {busy}", file=sys.stderr)
            return 3
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] in {"completed", "stopped"} else 1

    if args.command == "watch":
        stop = threading.Event()
        try:
            runner.watch(stop)
        except KeyboardInterrupt:
            stop.set()
        return 0

    if args.command == "status":
        from .service import OpsService
        svc = OpsService(config, runner)
        print(json.dumps({"status": svc.status(), "quality": svc.quality()}, ensure_ascii=False,
                         indent=2, default=str))
        return 0

    if args.command == "reprocess":
        from .service import OpsService
        svc = OpsService(config, runner)
        try:
            out = svc.reprocess(statuses=args.status, answer_ids=args.answer_id,
                                target_month=args.month, crawl_run_id=args.crawl_run_id,
                                stale=args.stale, run=False)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"Đã xếp lại {out['requeued']} answer vào hàng chờ.")
        if args.run and out["requeued"]:
            print(json.dumps(runner.run_once("cli-reprocess"), ensure_ascii=False, indent=2))
        return 0

    if args.command == "export":
        from .service import OpsService
        print(OpsService(config, runner).export(args.format, args.month))
        return 0

    if args.command == "ui":
        import uvicorn
        from .web.app import create_app
        uvicorn.run(create_app(config, runner), host=args.host or config.ui.host,
                    port=args.port or config.ui.port, log_level="info")
        return 0
    return 2
