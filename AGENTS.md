# Agent guide

`bilibili_atpy`：用你自己的B站账号每天挑一个视频、写一句十字以内的锐评、@ 几个朋友发在评论区，结果同步到 QQ 群。

文档规范见 [.github/engineering/STANDARD.md](.github/engineering/STANDARD.md)。

## 约定

- 包内一律相对导入。插件目录被 AstrBot 当作包加载，顶层包名在容器里 import 不到。
- 指令全在 `atpy` 组下（`/atpy 现在`），不占通用名。
- `requirements.txt` **手写**，理由见 `docs/RELEASING.md`。
- 网络请求只用 `aiohttp`。
- 数据落在 `data/plugin_data/astrbot_plugin_bilibili_atpy/`，不写插件目录。
- 登录态（`SESSDATA` / `bili_jct`）不进日志、不进异常消息、不进提交。

## 指令不响应的两类原因

**组别名带斜杠。** QQ 官方适配器在 `@机器人` 唤醒时 `wake_prefix = ""`，不剥 `message_str` 里的 `/`，拿到的是 `/atpy UMO`。只写组名 `atpy` 匹配不上，必须有 `_组别名 = {f"/{_组名}"}`。

**落空兜底。** `/atpy <不是子命令>` 时 `CommandGroupFilter` 返回 False，指令被跳过，消息进模型，输出与插件无关。`_落空兜底` 的 `filter` 所有出口必须 `return True`：语义是「这条消息是否由本组处理」，返回 False 会使整个指令组失效。新增子命令时 `atpy/兜底.子命令名` 要同步添加，`test_兜底不多不少` 校验。

**插件白名单。** 插件加载成功、handler 全部注册、`enabled` / `activated` 均为真时，指令仍可能全部无响应：每个 bot 的 `abconf_<uuid>.json` 中 `plugin_set` 是白名单，未列入的插件其所有 `AdapterMessageEvent` handler 在 `waking_check` 阶段被跳过，过滤器不执行；`cmd_config.json` 的 `["*"]` 被它覆盖。新装插件后必须加入。

排查顺序：abconf 的 `plugin_set` → registry 的 `enabled` / `activated` → filter 逻辑。

## 结构

- `main.py` — 入口：配置读取、后台调度、指令组、`recent_bili_critics` 工具
- `atpy/bili.py` — B站接口：WBI 签名、搜索、详情、发评论、点赞收藏、返回码翻译
- `atpy/pick.py` — 选片：五类关键词池、播放量与时间过滤、标题禁忌
- `atpy/critic.py` — 锐评：提示词、清洗输出、十字截断
- `atpy/store.py` — 落盘：历史记录与当日排期
- `atpy/兜底.py` — 指令落空的判据与提示
- `test/` — pytest 用例与真实接口验证脚本
- `docs/` — 更新日志、部署说明、发版说明

## 主循环是后台任务

AstrBot 没有内置调度器。`__init__` 中 `asyncio.create_task(self._调度())`，每 60 秒检查当天到点的档期，`terminate()` 中取消。指令与调度共用 `_跑一轮`。三条约束：

- **过期档期不补跑。** 超过十分钟的档期丢弃，否则容器重启后会一次执行多轮。
- **发评论失败不重试。** 跳过本轮，重试仅发生在「换关键词重搜」。同一轮重复发送会加快触发风控。
- **`取排期` 用 `None` 与 `[]` 区分「当天未排期」与「当天排了零轮」。** 合并为空列表会导致每分钟重排并写盘。

## 两处实测结论

- **选片不能用 `pubdate`。** 2026-10-21 实测：`pubdate` 排序返回的是刚上传、播放量为 0 的视频，达不到 `min_play`；`click` 排序全是早年高播放视频。只有 `totalrank` 同时满足播放量跨度与近期内容。改动选片逻辑前先运行 `uv run python test/verify_search.py`。
- **@ 是评论正文文本。** 评论接口 `x/v2/reply/add` 的 data 只有 `oid / type / message / csrf`，服务端解析 `message` 中的 `@昵称`，昵称必须完全一致。

## 模型调用

`_调模型` 直连 provider 的 `text_chat()`，不用 `tool_loop_agent`：此处只需文本到文本的转换，不需要工具；而 `tool_loop_agent` 会把当前会话挂载的全部工具 schema 加入请求并走 runner 循环。`recent_bili_critics` 是唯一注册的 LLM 工具，只读。

## config 必须可省

仓库没有 `_conf_schema.json` 时，`star_manager` 只传 `context`，不传 `config`。`__init__` 中把 `config` 声明为必需参数会抛出 `TypeError`，插件无法加载。
