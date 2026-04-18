#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import youtube_monitor_core
from youtube_monitor_core import MonitorEngine, json_dump, run_loop, write_default_config
from playwright.sync_api import sync_playwright


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

    download_parser = subparsers.add_parser("download", help="Download a YouTube video or audio")
    download_parser.add_argument("url_or_id", help="YouTube video URL or video ID")
    download_parser.add_argument("--audio", action="store_true", help="Download audio only as mp3")

    subtitles_parser = subparsers.add_parser("subtitles", help="Download subtitle files when available")
    subtitles_parser.add_argument("url_or_id", help="YouTube video URL or video ID")

    transcribe_parser = subparsers.add_parser("transcribe", help="Extract text from subtitles or audio")
    transcribe_parser.add_argument("url_or_id", help="YouTube video URL or video ID")
    transcribe_parser.add_argument("--no-subs", action="store_true", help="Skip subtitle attempt and transcribe from audio")
    transcribe_parser.add_argument("--model-size", default="small", help="faster-whisper model size")

    login_parser = subparsers.add_parser("prepare-login", help="Open a browser so the user can log into YouTube")
    login_parser.add_argument("--browser", default="chromium", help="Playwright browser type or channel hint")
    login_parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    login_parser.add_argument("--timeout-seconds", type=int, default=300, help="How long to keep the browser window open")
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
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

    if args.command == "prepare-login":
        profile_dir = Path.home() / ".local" / "share" / "chaunyyt-skill" / "browser-profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            browser_type = getattr(p, args.browser if args.browser in {"chromium", "firefox", "webkit"} else "chromium")
            launch_kwargs = {
                "user_data_dir": str(profile_dir),
                "headless": args.headless,
            }
            if args.browser in {"chrome", "msedge"}:
                launch_kwargs["channel"] = args.browser
                browser_type = p.chromium
            context = browser_type.launch_persistent_context(**launch_kwargs)
            page = context.new_page()
            page.goto("https://www.youtube.com/", wait_until="domcontentloaded", timeout=120000)
            page.wait_for_timeout(5000)
            time.sleep(max(args.timeout_seconds, 10))
            context.close()
        print_json(
            {
                "success": True,
                "message": "Browser session finished. If you logged into YouTube, yt-dlp can try to reuse that browser state next.",
                "profile_dir": str(profile_dir),
            }
        )
        return 0

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

    try:
        if args.command == "download":
            result = youtube_monitor_core.download_video(
                args.url_or_id,
                engine.paths["downloads_dir"],
                media_kind="audio" if args.audio else "video",
            )
            print_json(result)
            return 0 if result.get("success") else 1

        if args.command == "subtitles":
            result = youtube_monitor_core.download_subtitles(args.url_or_id, engine.paths["subtitles_dir"])
            print_json(result)
            return 0 if result.get("success") else 1

        if args.command == "transcribe":
            result = youtube_monitor_core.transcribe_video(
                args.url_or_id,
                engine.paths["transcripts_dir"],
                prefer_subtitles=not args.no_subs,
                model_size=args.model_size,
            )
            print_json(result)
            return 0 if result.get("success") else 1
    except Exception as exc:  # noqa: BLE001
        print_json({"success": False, "message": str(exc)})
        return 1

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
