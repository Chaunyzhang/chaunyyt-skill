# YouTube Monitor Architecture

## Chosen baseline

This skill uses one shared YouTube-only foundation:

1. watchlist config
2. collector per YouTube source
3. normalized event shape
4. stateful dedup
5. optional summarization
6. Markdown + JSONL outputs

## Why this baseline

- The official YouTube Data API exposes the uploaded-videos playlist path through `channels.list` plus `playlistItems.list`, which is a stable official way to enumerate recent channel uploads.
- Official YouTube RSS feeds are useful as a lightweight public fallback when we only need new-upload detection.
- Official `search.list` is useful for discovery and trend watching, but it is quota-expensive and should be scheduled much less frequently than channel polling.

## Recommended product path

### V1

- `run --once`
- local JSON config
- YouTube RSS or API polling
- YouTube keyword search with per-query cooldown
- local state and report generation

### V1.1

- xAI summary + relevance scoring
- per-query topic grouping
- push adapters for email, Telegram, Discord, Feishu
