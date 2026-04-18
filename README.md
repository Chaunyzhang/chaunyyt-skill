# Chauny YT Skill

一个面向个人研究与轻量监控的 YouTube skill，用来追踪固定频道和低频关键词发现。

## 这是什么

`chaunyyt-skill` 是一个基于 YouTube 官方 API / RSS 的监控 skill，适合：

- ✅ 盯固定频道
- ✅ 低频跑关键词发现
- ✅ 保存结构化事件
- ✅ 生成 Markdown 报告
- ✅ 在缺 API key 时显式停下并索要凭据

## 能干什么

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 固定频道监控 | ✅ | 通过 `channel_id` 跟踪新视频 |
| 关键词发现 | ✅ | 通过 `search.list` 低频搜索 |
| 去重 | ✅ | 跨运行状态去重 |
| JSONL 事件落盘 | ✅ | 保存结构化视频记录 |
| Markdown 报告 | ✅ | 输出最新结果摘要 |
| 凭据门控 | ✅ | 缺 `YOUTUBE_API_KEY` 时直接停下 |
| xAI 摘要预留 | ✅ | 配置层已预留 |
| 视频下载 | ❌ | 当前未实现 |
| 音频转写 | ❌ | 当前未实现 |
| 热门榜专用模式 | ❌ | 当前以频道/搜索为主 |

## 适合谁

- ✅ 想固定盯几个频道
- ✅ 想低频搜索某些关键词
- ✅ 关注成本与配额控制
- ✅ 需要一个稳定的 YouTube 监控底座

## 工作流

| 步骤 | 操作 | 结果 |
| --- | --- | --- |
| 1 | `init` | 生成配置 |
| 2 | `check` | 校验配置、凭据、搜索配额估算 |
| 3 | `run --once` | 拉最新频道视频或搜索结果 |
| 4 | 重复运行 | 自动去重并更新报告 |

## 常用命令

```powershell
python scripts/youtube_monitor_cli.py init --config .\youtube-monitor-config.json
python scripts/youtube_monitor_cli.py check --config .\youtube-monitor-config.json
python scripts/youtube_monitor_cli.py run --config .\youtube-monitor-config.json --once
```

## 配置重点

| 配置项 | 用途 |
| --- | --- |
| `youtube.channels` | 固定频道监控列表 |
| `youtube.searches` | 低频关键词搜索列表 |
| `min_interval_seconds` | 控制搜索成本 |
| `output_dir` | 事件、状态、报告输出目录 |

## 输出结果

| 输出 | 用途 |
| --- | --- |
| `events/events.jsonl` | 保存视频结构化记录 |
| `state/state.json` | 去重与游标状态 |
| `reports/latest-report.md` | 最新监控报告 |

## 使用建议

- ✅ 固定频道用 API 或 RSS 常规轮询
- ✅ 搜索只做发现，不要高频跑
- ✅ 先用 `run --once` 测试
- ✅ 配额敏感时优先频道监控

## 当前限制

- ❌ 不下载视频文件
- ❌ 不提取字幕或转文案
- ❌ 不做实时热门榜

## 仓库定位

这是一个：

> 小而稳、对频道监控友好、对配额敏感、适合个人和小团队的 YouTube 监控 skill。
