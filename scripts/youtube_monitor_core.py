from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_CONFIG = {
    "output_dir": "./youtube-monitor-output",
    "polling": {
        "interval_seconds": 1800,
    },
    "summarization": {
        "enabled": False,
        "provider": "xai-compatible",
        "api_key_env": "XAI_API_KEY",
        "base_url": "https://api.x.ai/v1",
        "model": "grok-3-mini",
        "temperature": 0.2,
    },
    "youtube": {
        "enabled": True,
        "api_key_env": "YOUTUBE_API_KEY",
        "max_results": 10,
        "channels": [
            {
                "label": "Example Channel",
                "channel_id": "UCxxxxxxxxxxxxxxxxxxxxxx",
                "source": "rss",
            }
        ],
        "searches": [
            {
                "label": "Example Topic Search",
                "query": "openai agents",
                "max_results": 10,
                "min_interval_seconds": 43200,
            }
        ],
    },
}


USER_AGENT = "youtube-monitor/0.1"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def json_dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dump(data) + "\n", encoding="utf-8")


def append_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def http_json(
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if params:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{url}?{query}"
    data = None
    base_headers = {"User-Agent": USER_AGENT}
    if headers:
        base_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        base_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=base_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error for {url}: {exc}") from exc


def http_text(url: str, *, headers: Optional[Dict[str, str]] = None) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error for {url}: {exc}") from exc


def ensure_runtime_paths(output_dir: Path) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    state_dir = output_dir / "state"
    reports_dir = output_dir / "reports"
    events_dir = output_dir / "events"
    for path in (state_dir, reports_dir, events_dir):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "output_dir": output_dir,
        "state": state_dir / "state.json",
        "events": events_dir / "events.jsonl",
        "report": reports_dir / "latest-report.md",
    }


def load_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    return json.loads(config_path.read_text(encoding="utf-8-sig"))


def write_default_config(config_path: Path) -> Path:
    if config_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing config: {config_path}")
    write_json(config_path, DEFAULT_CONFIG)
    return config_path


def load_state(state_path: Path) -> Dict[str, Any]:
    return read_json(
        state_path,
        {
            "seen_ids": [],
            "youtube_uploads_playlists": {},
            "source_last_run": {},
            "last_run_at": None,
        },
    )


def save_state(state_path: Path, state: Dict[str, Any]) -> None:
    state = dict(state)
    state["seen_ids"] = sorted(set(state.get("seen_ids", [])))
    state["last_run_at"] = utc_now_iso()
    write_json(state_path, state)


def normalize_seen_key(source_id: str, item_id: str) -> str:
    return f"youtube:{source_id}:{item_id}"


def missing_required_credentials(config: Dict[str, Any]) -> List[Dict[str, str]]:
    missing: List[Dict[str, str]] = []
    youtube_env = config.get("youtube", {}).get("api_key_env", "YOUTUBE_API_KEY")
    if config.get("youtube", {}).get("enabled", True) and not os.getenv(youtube_env):
        missing.append(
            {
                "kind": "api_key",
                "env_var": youtube_env,
                "label": "YouTube API key",
                "when_to_ask": "activation",
            }
        )
    return missing


@dataclass
class SummaryResult:
    summary: Optional[Dict[str, Any]]
    error: Optional[str] = None


class XAISummarizer:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config

    def enabled(self) -> bool:
        if not self.config.get("enabled"):
            return False
        return bool(os.getenv(self.config.get("api_key_env", "")))

    def summarize(self, item: Dict[str, Any]) -> SummaryResult:
        if not self.enabled():
            return SummaryResult(summary=None)
        api_key = os.getenv(self.config["api_key_env"], "")
        base_url = self.config.get("base_url", "https://api.x.ai/v1").rstrip("/")
        prompt = (
            "You summarize monitored YouTube videos for fast triage. "
            "Return strict JSON with keys: summary, bullets, relevance_score, tags. "
            "summary must be <= 120 Chinese characters."
        )
        user_payload = {
            "author": item.get("author"),
            "title": item.get("title"),
            "text": item.get("text"),
            "published_at": item.get("published_at"),
            "url": item.get("url"),
        }
        try:
            response = http_json(
                f"{base_url}/chat/completions",
                method="POST",
                headers={"Authorization": f"Bearer {api_key}"},
                payload={
                    "model": self.config.get("model", "grok-3-mini"),
                    "temperature": self.config.get("temperature", 0.2),
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                    ],
                },
            )
            content = response["choices"][0]["message"]["content"]
            return SummaryResult(summary=json.loads(content))
        except Exception as exc:  # noqa: BLE001
            return SummaryResult(summary=None, error=str(exc))


class YouTubeCollector:
    def __init__(self, config: Dict[str, Any], state: Dict[str, Any]) -> None:
        self.config = config
        self.state = state

    def collect(self) -> List[Dict[str, Any]]:
        if not self.config.get("enabled", True):
            return []
        items: List[Dict[str, Any]] = []
        api_key = os.getenv(self.config.get("api_key_env", ""))
        max_results = self.config.get("max_results", 10)
        for channel in self.config.get("channels", []):
            source = channel.get("source", "rss")
            if source == "api" and api_key:
                items.extend(self._collect_from_api(channel, api_key, max_results))
            else:
                items.extend(self._collect_from_rss(channel))
        if api_key:
            items.extend(self._collect_search_queries(api_key))
        return items

    def _collect_search_queries(self, api_key: str) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for search in self.config.get("searches", []):
            if not self._search_due(search):
                continue
            max_results = search.get("max_results", self.config.get("max_results", 10))
            response = http_json(
                f"{YOUTUBE_API_BASE}/search",
                params={
                    "part": "snippet",
                    "q": search["query"],
                    "type": "video",
                    "order": search.get("order", "date"),
                    "publishedAfter": search.get("published_after"),
                    "maxResults": max_results,
                    "key": api_key,
                },
            )
            for row in response.get("items", []):
                item_id = row.get("id", {}).get("videoId")
                snippet = row.get("snippet", {})
                if not item_id:
                    continue
                normalized.append(
                    {
                        "platform": "youtube",
                        "source_type": "search",
                        "source_id": search["query"],
                        "source_label": search.get("label") or search["query"],
                        "item_id": item_id,
                        "author": snippet.get("channelTitle"),
                        "title": snippet.get("title"),
                        "text": snippet.get("description", ""),
                        "published_at": snippet.get("publishedAt"),
                        "url": f"https://www.youtube.com/watch?v={item_id}",
                        "metrics": {},
                        "raw": row,
                    }
                )
            self._mark_search_run(search)
        return normalized

    def _search_due(self, search: Dict[str, Any]) -> bool:
        min_interval = int(search.get("min_interval_seconds", 43200))
        if min_interval <= 0:
            return True
        source_last_run = self.state.setdefault("source_last_run", {})
        state_key = f"youtube-search:{search['query']}"
        last_run = source_last_run.get(state_key)
        if not last_run:
            return True
        try:
            last_run_ts = datetime.fromisoformat(last_run.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return True
        return (time.time() - last_run_ts) >= min_interval

    def _mark_search_run(self, search: Dict[str, Any]) -> None:
        state_key = f"youtube-search:{search['query']}"
        self.state.setdefault("source_last_run", {})[state_key] = utc_now_iso()

    def _collect_from_api(
        self,
        channel: Dict[str, Any],
        api_key: str,
        max_results: int,
    ) -> List[Dict[str, Any]]:
        uploads_playlist_id = channel.get("uploads_playlist_id")
        channel_id = channel.get("channel_id")
        if not uploads_playlist_id:
            uploads_playlist_id = self.state.setdefault("youtube_uploads_playlists", {}).get(channel_id or "")
        if not uploads_playlist_id:
            if not channel_id:
                raise RuntimeError(f"YouTube channel is missing channel_id: {channel}")
            response = http_json(
                f"{YOUTUBE_API_BASE}/channels",
                params={
                    "part": "contentDetails,snippet",
                    "id": channel_id,
                    "key": api_key,
                },
            )
            items = response.get("items", [])
            if not items:
                raise RuntimeError(f"No YouTube channel found for channel_id={channel_id}")
            uploads_playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
            self.state.setdefault("youtube_uploads_playlists", {})[channel_id] = uploads_playlist_id

        response = http_json(
            f"{YOUTUBE_API_BASE}/playlistItems",
            params={
                "part": "snippet,contentDetails",
                "playlistId": uploads_playlist_id,
                "maxResults": max_results,
                "key": api_key,
            },
        )
        normalized: List[Dict[str, Any]] = []
        for row in response.get("items", []):
            snippet = row.get("snippet", {})
            video_id = (
                row.get("contentDetails", {}).get("videoId")
                or snippet.get("resourceId", {}).get("videoId")
            )
            if not video_id:
                continue
            normalized.append(
                {
                    "platform": "youtube",
                    "source_type": "channel",
                    "source_id": channel.get("channel_id") or uploads_playlist_id,
                    "source_label": channel.get("label") or snippet.get("channelTitle"),
                    "item_id": video_id,
                    "author": snippet.get("channelTitle"),
                    "title": snippet.get("title"),
                    "text": snippet.get("description", ""),
                    "published_at": snippet.get("publishedAt"),
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "metrics": {},
                    "raw": row,
                }
            )
        return normalized

    def _collect_from_rss(self, channel: Dict[str, Any]) -> List[Dict[str, Any]]:
        rss_url = channel.get("rss_url")
        channel_id = channel.get("channel_id")
        if not rss_url:
            if not channel_id:
                raise RuntimeError(f"YouTube RSS source requires channel_id or rss_url: {channel}")
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        xml_text = http_text(rss_url)
        root = ET.fromstring(xml_text)
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "media": "http://search.yahoo.com/mrss/",
            "yt": "http://www.youtube.com/xml/schemas/2015",
        }
        normalized: List[Dict[str, Any]] = []
        for entry in root.findall("atom:entry", ns):
            video_id = entry.findtext("yt:videoId", default="", namespaces=ns)
            title = entry.findtext("atom:title", default="", namespaces=ns)
            author_name = entry.findtext("atom:author/atom:name", default="", namespaces=ns)
            published_at = entry.findtext("atom:published", default="", namespaces=ns)
            link = entry.find("atom:link", ns)
            url = link.attrib.get("href", f"https://www.youtube.com/watch?v={video_id}") if link is not None else ""
            description = entry.findtext("media:group/media:description", default="", namespaces=ns)
            normalized.append(
                {
                    "platform": "youtube",
                    "source_type": "channel",
                    "source_id": channel_id or rss_url,
                    "source_label": channel.get("label") or author_name,
                    "item_id": video_id,
                    "author": author_name,
                    "title": title,
                    "text": description,
                    "published_at": published_at,
                    "url": url,
                    "metrics": {},
                    "raw": {"rss_url": rss_url},
                }
            )
        return normalized


class MonitorEngine:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.config = load_config(config_path)
        self.paths = ensure_runtime_paths(Path(self.config["output_dir"]).resolve())
        self.state = load_state(self.paths["state"])
        self.summarizer = XAISummarizer(self.config.get("summarization", {}))

    def check(self) -> Dict[str, Any]:
        youtube_env = self.config.get("youtube", {}).get("api_key_env", "YOUTUBE_API_KEY")
        summary_env = self.config.get("summarization", {}).get("api_key_env", "XAI_API_KEY")
        youtube_searches = self.config.get("youtube", {}).get("searches", [])
        estimated_search_units_per_day = 0.0
        for search in youtube_searches:
            interval = int(search.get("min_interval_seconds", 43200))
            if interval > 0:
                estimated_search_units_per_day += (86400 / interval) * 100
        missing_credentials = missing_required_credentials(self.config)
        return {
            "success": True,
            "config_path": str(self.config_path),
            "output_dir": str(self.paths["output_dir"]),
            "required_env": {
                "youtube_api": youtube_env,
                "xai_api_key": summary_env if self.config.get("summarization", {}).get("enabled") else None,
            },
            "env_status": {
                "youtube_api": bool(os.getenv(youtube_env)),
                "xai_api_key": bool(os.getenv(summary_env)) if self.config.get("summarization", {}).get("enabled") else False,
            },
            "needs_credentials": bool(missing_credentials),
            "missing_credentials": missing_credentials,
            "activation_prompt_hint": "If youtube_api is missing, pause and ask the user for the YouTube API key during skill activation before running collection.",
            "youtube_channels": len(self.config.get("youtube", {}).get("channels", [])),
            "youtube_searches": len(youtube_searches),
            "estimated_youtube_search_units_per_day": round(estimated_search_units_per_day, 2),
            "summarization_enabled": self.summarizer.enabled(),
        }

    def run_once(self) -> Dict[str, Any]:
        missing_credentials = missing_required_credentials(self.config)
        if missing_credentials:
            return {
                "success": False,
                "status": "needs_credentials",
                "message": "Missing required credentials. Ask the user for the YouTube API key before continuing.",
                "missing_credentials": missing_credentials,
            }
        collected: List[Dict[str, Any]] = []
        errors: List[str] = []
        try:
            collected.extend(YouTubeCollector(self.config.get("youtube", {}), self.state).collect())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"YouTube collector failed: {exc}")

        new_items: List[Dict[str, Any]] = []
        seen_ids = set(self.state.get("seen_ids", []))
        for item in sorted(collected, key=lambda row: row.get("published_at") or "", reverse=True):
            seen_key = normalize_seen_key(item["source_id"], item["item_id"])
            if seen_key in seen_ids:
                continue
            summary = self.summarizer.summarize(item)
            if summary.summary is not None:
                item["summary"] = summary.summary
            if summary.error:
                item["summary_error"] = summary.error
            item["seen_key"] = seen_key
            item["collected_at"] = utc_now_iso()
            new_items.append(item)
            seen_ids.add(seen_key)

        self.state["seen_ids"] = sorted(seen_ids)
        save_state(self.paths["state"], self.state)
        if new_items:
            append_jsonl(self.paths["events"], new_items)
        report = render_report(new_items, errors)
        self.paths["report"].write_text(report, encoding="utf-8")
        return {
            "success": not errors,
            "new_items": len(new_items),
            "total_collected": len(collected),
            "errors": errors,
            "report_path": str(self.paths["report"]),
            "events_path": str(self.paths["events"]),
            "state_path": str(self.paths["state"]),
        }


def render_report(items: List[Dict[str, Any]], errors: List[str]) -> str:
    lines = [
        "# YouTube Monitor Report",
        "",
        f"- Generated at: {utc_now_iso()}",
        f"- New items: {len(items)}",
        f"- Errors: {len(errors)}",
        "",
    ]
    if errors:
        lines.extend(["## Errors", ""])
        for error in errors:
            lines.append(f"- {error}")
        lines.append("")
    lines.extend(["## New Items", ""])
    if not items:
        lines.append("- No new items this run.")
        lines.append("")
        return "\n".join(lines)

    for item in items:
        title = item.get("title") or "Untitled"
        lines.append(f"### [YouTube] {title}")
        lines.append("")
        lines.append(f"- Author: {item.get('author')}")
        lines.append(f"- Source: {item.get('source_label')}")
        lines.append(f"- Published: {item.get('published_at')}")
        lines.append(f"- URL: {item.get('url')}")
        if item.get("summary", {}).get("summary"):
            lines.append(f"- Summary: {item['summary']['summary']}")
        text = item.get("text", "")
        if text:
            preview = text.replace("\n", " ").strip()
            lines.append(f"- Preview: {preview[:220]}{'...' if len(preview) > 220 else ''}")
        lines.append("")
    return "\n".join(lines)


def run_loop(config_path: Path, interval_seconds: Optional[int] = None) -> int:
    while True:
        engine = MonitorEngine(config_path)
        result = engine.run_once()
        print(json_dump(result))
        wait_seconds = interval_seconds or engine.config.get("polling", {}).get("interval_seconds", 1800)
        if wait_seconds <= 0:
            return 0 if result.get("success") else 1
        time.sleep(wait_seconds)
