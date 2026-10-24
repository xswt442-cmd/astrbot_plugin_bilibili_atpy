# atpy

用你自己的B站账号，每天挑一个视频，让模型写一句十字以内的锐评，@ 几个朋友发在评论区，再把结果同步到 QQ 群。

## 一轮做什么

1. 按当天类别抽一个关键词（五类按日期轮转：搞笑搞怪 / 莫名其妙 / 二游 / 王者荣耀 / 无畏契约）
2. 搜视频，丢掉播放量太低和太高的
3. 把标题、UP主、分区、简介交给模型，换一句点评
4. 拼成 `@张三 @李四 这不科学` 发到评论区，顺手点赞收藏
5. 在配置的通知会话说一声
6. 记下 bvid，同一个视频不会发第二次

默认每天一条，时间在活跃时段内随机取。

## 配置

| 配置项 | 说明 |
|---|---|
| `sessdata` / `bili_jct` | B站登录态。登录后 F12 → Application → Cookies 复制 |
| `friends` | 朋友的B站昵称，逗号分隔，必须一字不差 |
| `notify_umo` | 通知发到哪个会话。在群里发 `/atpy UMO` 取整串 |
| `rounds_min` / `rounds_max` | 每天几条，默认 1-1 |
| `active_start_hour` / `active_end_hour` | 活跃时段，默认 9-23 点 |
| `min_play` / `max_play` | 播放量区间，默认 10000-5000000 |
| `max_days_old` | 只要几天内发布的，默认 0（不限） |
| `keywords` | 自定义搜索词，逗号分隔。填了就不再按内置五类轮转 |
| `provider_id` | 写锐评用哪个模型，留空用第一个已加载的 |
| `dry_run` | 预览模式，只选片和写评，不发评论 |

第一次部署建议先开 `dry_run` 跑一天，看选片和锐评对不对味再关掉。

## 指令

```
/atpy 现在    跑一轮，会真的发评论
/atpy 预览    只选片写评，不发
/atpy 最近    最近发过的五条
/atpy 状态    登录态、今日类别与排期
/atpy UMO     取会话标识
/atpy 帮助    列出全部指令
```

模型也能调 `recent_bili_critics` 查最近发过什么。

## 注意

- @ 就是正文文本，由B站服务端解析。昵称错一个字就只是纯文本，对方收不到通知
- 带 @ 的评论是B站判定「营销引流」的高危行为，一天一条是保守值，别急着往上加
- 不要用主号

## 开发

```sh
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

真实接口验证（不需要登录态）：

```sh
uv run python test/verify_search.py
```

发版流程见 `docs/RELEASING.md`，更新记录见 `docs/CHANGELOG.md`。
