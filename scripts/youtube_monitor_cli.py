#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import youtube_monitor_core
from youtube_monitor_core import MonitorEngine, json_dump, run_loop, write_default_config
from playwright.sync_api import sync_playwright


def print_json(data):
    print(json_dump(data))


def open_real_browser(browser_name: str, url: str) -> dict:
    browser_name = browser_name.lower()
    executable = shutil.which(browser_name)
    if executable:
        subprocess.Popen([executable, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"success": True, "browser": browser_name, "mode": "system-browser", "url": url}
    if browser_name == "chrome":
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
    elif browser_name == "msedge":
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        ]
    else:
        candidates = []
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            subprocess.Popen([candidate, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"success": True, "browser": browser_name, "mode": "system-browser", "url": url}
    webbrowser.open(url)
    return {"success": True, "browser": browser_name, "mode": "default-browser", "url": url}


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

    remote_parser = subparsers.add_parser("transcribe-remote-url", help="Send a discovered remote media URL directly to DashScope")
    remote_parser.add_argument("remote_url", help="Audio or video URL captured from browser devtools/network")

    subtitle_url_parser = subparsers.add_parser("subtitle-text-url", help="Convert a discovered subtitle URL into plain text")
    subtitle_url_parser.add_argument("subtitle_url", help="Subtitle URL captured from browser devtools/network")

    login_parser = subparsers.add_parser("prepare-login", help="Open a browser so the user can log into YouTube")
    login_parser.add_argument("--browser", default="chromium", help="Playwright browser type or channel hint")
    login_parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    login_parser.add_argument("--timeout-seconds", type=int, default=300, help="How long to keep the browser window open")

    probe_parser = subparsers.add_parser("probe-browser-media", help="Open a YouTube page in a browser and capture subtitle/media request URLs")
    probe_parser.add_argument("video_url", help="YouTube watch URL")
    probe_parser.add_argument("--browser", default="chromium", help="Playwright browser type or channel hint")
    probe_parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    probe_parser.add_argument("--capture-seconds", type=int, default=15, help="How long to observe requests after load")
    return parser


def probe_browser_media(video_url: str, browser_name: str = "chromium", headless: bool = False, capture_seconds: int = 15) -> dict:
    hits = []
    with sync_playwright() as p:
        browser_type = getattr(p, browser_name if browser_name in {"chromium", "firefox", "webkit"} else "chromium")
        launch_kwargs = {"headless": headless}
        if browser_name in {"chrome", "msedge"}:
            launch_kwargs["channel"] = browser_name
            browser_type = p.chromium
        browser = browser_type.launch(**launch_kwargs)
        page = browser.new_page()

        def on_response(resp):
            url = resp.url
            if "googlevideo.com" in url or "timedtext" in url or "caption" in url:
                hits.append(url)

        page.on("response", on_response)
        page.goto(video_url, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(4000)
        try:
            page.keyboard.press("k")
        except Exception:
            pass
        page.wait_for_timeout(max(capture_seconds, 5) * 1000)
        browser.close()

    subtitle_urls = [url for url in hits if "timedtext" in url or "caption" in url]
    media_urls = [url for url in hits if "googlevideo.com" in url]
    return {
        "success": True,
        "video_url": video_url,
        "subtitle_urls": subtitle_urls,
        "media_urls": media_urls,
        "captured_requests": hits[:50],
    }


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
        if args.browser in {"chrome", "msedge"}:
            open_result = open_real_browser(args.browser, "https://www.youtube.com/")
            time.sleep(max(args.timeout_seconds, 10))
            print_json(
                {
                    **open_result,
                    "message": "Browser session window opened. If you logged into YouTube, yt-dlp can try to reuse that browser state next.",
                }
            )
            return 0

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
        if args.command == "probe-browser-media":
            result = probe_browser_media(
                args.video_url,
                browser_name=args.browser,
                headless=args.headless,
                capture_seconds=args.capture_seconds,
            )
            print_json(result)
            return 0 if result.get("success") else 1

        if args.command == "transcribe-remote-url":
            result = youtube_monitor_core.transcribe_remote_media_url(args.remote_url)
            print_json(result)
            return 0 if result.get("success") else 1

        if args.command == "subtitle-text-url":
            result = youtube_monitor_core.vtt_text_from_url(args.subtitle_url)
            print_json(result)
            return 0 if result.get("success") else 1

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
