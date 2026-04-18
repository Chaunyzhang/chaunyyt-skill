# Chauny YT Skill

一个面向个人研究与轻量监控的 YouTube skill，用来追踪固定频道、低频关键词发现、下载视频、提取字幕和转文案。

## 这是什么

`chaunyyt-skill` 是一个基于 YouTube 官方 API / RSS 的监控与内容提取工具，适合：

- ✅ 盯固定频道
- ✅ 低频跑关键词发现
- ✅ 保存结构化事件
- ✅ 下载视频或音频
- ✅ 提取字幕
- ✅ 转成文本稿

## 能干什么

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 固定频道监控 | ✅ | 通过 `channel_id` 跟踪新视频 |
| 关键词发现 | ✅ | 通过 `search.list` 低频搜索 |
| 去重 | ✅ | 跨运行状态去重 |
| JSONL 事件落盘 | ✅ | 保存结构化视频记录 |
| Markdown 报告 | ✅ | 输出最新结果摘要 |
| 凭据门控 | ✅ | 缺 `YOUTUBE_API_KEY` 时直接停下 |
| 视频下载 | ✅ | 通过 `yt-dlp` 下载视频 |
| 音频下载 | ✅ | 通过 `yt-dlp` 下载音频 |
| 字幕提取 | ✅ | 优先下载官方/自动字幕 |
| 文案提取 | ✅ | 优先字幕，其次音频 URL、视频 URL，最后本地媒体 + DashScope |
| xAI 摘要预留 | ✅ | 配置层已预留 |
| 热门榜专用模式 | ❌ | 当前以频道/搜索为主 |

## 适合谁

- ✅ 想固定盯几个频道
- ✅ 想低频搜索某些关键词
- ✅ 想把视频继续转成文案
- ✅ 关注成本与配额控制
- ✅ 需要一个稳定的 YouTube 监控底座

## 工作流

| 步骤 | 操作 | 结果 |
| --- | --- | --- |
| 1 | `init` | 生成配置 |
| 2 | `check` | 校验配置、凭据、搜索配额估算 |
| 3 | `prepare-login` | 自动打开浏览器让用户登录 YouTube |
| 4 | `run --once` | 拉最新频道视频或搜索结果 |
| 5 | `download` | 下载视频或音频 |
| 6 | `subtitles` | 下载字幕文件 |
| 7 | `transcribe` | 生成文本稿 |

## 常用命令

```powershell
python scripts/youtube_monitor_cli.py init --config .\youtube-monitor-config.json
python scripts/youtube_monitor_cli.py check --config .\youtube-monitor-config.json
python scripts/youtube_monitor_cli.py prepare-login --browser chrome
python scripts/youtube_monitor_cli.py run --config .\youtube-monitor-config.json --once
python scripts/youtube_monitor_cli.py download "<youtube_url>"
python scripts/youtube_monitor_cli.py download "<youtube_url>" --audio
python scripts/youtube_monitor_cli.py subtitles "<youtube_url>"
python scripts/youtube_monitor_cli.py transcribe "<youtube_url>"
```

## 配置重点

| 配置项 | 用途 |
| --- | --- |
| `youtube.channels` | 固定频道监控列表 |
| `youtube.searches` | 低频关键词搜索列表 |
| `min_interval_seconds` | 控制搜索成本 |
| `output_dir` | 事件、状态、报告、下载输出目录 |

## 输出结果

| 输出 | 用途 |
| --- | --- |
| `events/events.jsonl` | 保存视频结构化记录 |
| `state/state.json` | 去重与游标状态 |
| `reports/latest-report.md` | 最新监控报告 |
| `downloads/` | 下载的视频或音频 |
| `subtitles/` | 下载的字幕文件 |
| `transcripts/` | 生成的文本稿 |

## 使用建议

- ✅ 固定频道用 API 或 RSS 常规轮询
- ✅ 搜索只做发现，不要高频跑
- ✅ 先用 `run --once` 测试
- ✅ 真正重要的视频再下载/转写
- ✅ 优先先试字幕，再试音频 URL / 视频 URL，最后再回退本地媒体 + DashScope
- ✅ 如果 YouTube 要求登录确认不是 bot，先跑 `prepare-login`，再设置 `YT_DLP_COOKIES_FROM_BROWSER=chrome` 或 `edge`

## 当前限制

- ❌ 不做实时热门榜
- ❌ 依赖本机存在 `yt-dlp`、`ffmpeg`
- ❌ 音频转写依赖 `DASHSCOPE_API_KEY`

## 仓库定位

这是一个：

> 小而稳、对频道监控友好、支持后续下载与文案提取、适合个人和小团队的 YouTube 监控 skill。
