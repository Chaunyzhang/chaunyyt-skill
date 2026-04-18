#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from youtube_monitor_core import MonitorEngine, json_dump, run_loop, write_default_config


def print_json(data):
    print(json_dump(data))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stateful YouTube watchlist monitor")
    parser.add_argument(
        "--config",
        default="youtube-monitor-config.json",
        help="Path to the monitor config JSON file",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Write a sample config")
    init_parser.add_argument("--force-path", help="Optional explicit path for init output")

    subparsers.add_parser("check", help="Validate config and environment")

    run_parser = subparsers.add_parser("run", help="Run monitoring")
    run_parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    run_parser.add_argument(
        "--interval-seconds",
        type=int,
        default=None,
        help="Override polling interval for loop mode",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config_override = getattr(args, "force_path", None)
    config_path = Path(config_override or args.config).resolve()

    if args.command == "init":
        write_default_config(config_path)
        print_json(
            {
                "success": True,
                "message": "Sample config created",
                "config_path": str(config_path),
            }
        )
        return 0

    engine = MonitorEngine(config_path)

    if args.command == "check":
        result = engine.check()
        print_json(result)
        return 2 if result.get("needs_credentials") else (0 if result.get("success") else 1)

    if args.command == "run":
        if args.once:
            result = engine.run_once()
            print_json(result)
            if result.get("status") == "needs_credentials":
                return 2
            return 0 if result.get("success") else 1
        return run_loop(config_path, interval_seconds=args.interval_seconds)

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
