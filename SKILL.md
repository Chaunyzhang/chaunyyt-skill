---
name: chaunyyt-skill
description: Monitor a fixed watchlist of YouTube channels and low-frequency YouTube keyword searches with stateful deduplication, scheduled polling, optional xAI summarization, and report generation. Use when Codex needs to continuously watch selected YouTube creators or run quota-aware discovery searches, detect newly published videos, summarize or score relevant ones, and keep a reusable monitoring baseline. When credentials are missing, ask for the YouTube API key at skill activation time instead of assuming it is already configured.
---

# Chauny YT Skill

## First Move

Always initialize or inspect the watchlist config before running a monitor cycle:

```powershell
python scripts/youtube_monitor_cli.py init
python scripts/youtube_monitor_cli.py check
```

Do not start a long-running monitor before `check` succeeds.

## What This Skill Covers

- Monitor selected YouTube channels by official API or official RSS feed.
- Monitor selected YouTube keyword searches at a controlled low frequency.
- Deduplicate items across runs with a local state file.
- Save normalized JSONL events and Markdown reports.
- Optionally call an xAI-compatible endpoint to summarize or score each video.
- Surface missing credentials during skill activation so the same onboarding flow works for every user.

## Safety Defaults

- Prefer official APIs first.
- Keep monitoring read-only.
- Prefer `run --once` plus an external scheduler over a permanent in-process daemon unless the user explicitly wants a foreground loop.
- Treat channel monitoring and keyword search as separate cost profiles.
- When `YOUTUBE_API_KEY` is missing, request it during activation and do not guess or silently scrape as the default fallback.
- When `YOUTUBE_API_KEY` is missing, stop the real run immediately, ask the user for it, and resume only after the credential is provided.

## Workflow

### 1. Create the config

```powershell
python scripts/youtube_monitor_cli.py init --config .\youtube-monitor-config.json
```

Then edit the generated JSON:

- Add YouTube `channel_id` values for creators you care about.
- Add keyword searches only for discovery use cases.
- Keep searches low-frequency with `min_interval_seconds`.
- Set `summarization.enabled` to `true` only after the xAI endpoint and API key env vars are ready.

### 2. Validate credentials and inputs

```powershell
python scripts/youtube_monitor_cli.py check --config .\youtube-monitor-config.json
```

This verifies:

- config structure
- output directory
- which env vars are expected
- whether the monitor can run with current credentials
- estimated search quota burn per day

If `youtube_api` is missing, the activation flow should ask the user for the YouTube API key in the same standardized way every time.

Expected behavior:

- `check` should report `needs_credentials: true`
- `run --once` should stop with `status: needs_credentials`
- do not continue into collection with partial assumptions

### 3. Run one cycle

```powershell
python scripts/youtube_monitor_cli.py run --config .\youtube-monitor-config.json --once
```

Use this first. It is the safest way to confirm:

- channels resolve
- search cooldown behavior works
- API auth works
- dedup works
- summaries look acceptable

### 4. Run continuously when needed

Foreground loop:

```powershell
python scripts/youtube_monitor_cli.py run --config .\youtube-monitor-config.json
```

Recommended production shape:

- schedule `python scripts/youtube_monitor_cli.py run --config <path> --once`
- interval: 15 to 60 minutes for channel monitoring
- search cooldowns should usually be 6 to 24 hours
- keep state and reports in the configured output directory

## Config Notes

Three supported collection paths:

1. Official API for channels
2. Official RSS feed for channels
3. Official keyword search via `search.list`

Treat YouTube search separately from channel monitoring:

- channel monitoring is suitable for frequent polling
- keyword search is expensive and should run at low frequency
- default recommendation: every 6 to 24 hours per query

Typical config shape:

```json
{
  "youtube": {
    "channels": [
      {
        "label": "Latent Space",
        "channel_id": "UC...",
        "source": "api"
      }
    ],
    "searches": [
      {
        "label": "OpenAI agents",
        "query": "openai agents",
        "max_results": 10,
        "min_interval_seconds": 43200
      }
    ]
  }
}
```

Remember:

- `search.list` is the expensive path in YouTube quota terms
- do not schedule per-keyword search every few minutes
- use channels for known creators and search for discovery only

## xAI

The summarizer is OpenAI-compatible by default and can point at xAI-compatible chat completions via config. Typical env vars:

```powershell
$env:XAI_API_KEY="..."
$env:XAI_BASE_URL="https://api.x.ai/v1"
```

If the API key is missing, monitoring still runs and simply skips summaries.

## Resources (optional)

### scripts/

- `youtube_monitor_cli.py`: operator entrypoint
- `youtube_monitor_core.py`: collectors, state, dedup, summaries, reports

### references/

- `architecture.md`: reusable YouTube monitoring decisions and source-backed rationale
