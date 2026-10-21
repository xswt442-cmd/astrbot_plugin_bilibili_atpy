# Agent guide

`bilibili_atpy` 是 AstrBot 插件，用你自己的B站账号每天随机挑怪视频、写一句
十字以内的锐评、@ 几个朋友发在评论区，并把结果同步到 QQ 群。

## 约定

- 包内一律用相对导入。插件目录被 AstrBot 当成包加载，顶层包名在容器里
  import 不到。
- 指令全在 `atpy` 指令组下（`/atpy 现在`），不占用通用名字。
- `requirements.txt` **手写**，理由见 `docs/RELEASING.md`。
- 网络请求只用 `aiohttp`。
- 持久化数据放 AstrBot 的 `data/plugin_data/astrbot_plugin_bilibili_atpy/`，
  不放插件目录。
- 登录态（`SESSDATA` / `bili_jct`）不写日志、不进异常消息、不进提交。

## 结构

```
main.py              插件入口：配置读取、后台调度、指令组、recent_bili_critics 工具
atpy/bili.py         B站接口：WBI 签名、搜索、详情、发评论、返回码翻译
atpy/pick.py         选片：关键词池、播放量与时间过滤、标题禁忌词
atpy/critic.py       锐评：提示词、清洗模型输出、十字截断
atpy/store.py        落盘：历史记录与当日排期
test/                pytest 用例与真实接口验证脚本
docs/                更新日志与发版说明
```

## 主循环是后台任务，不是指令

AstrBot 没有内置 scheduler。`__init__` 里 `asyncio.create_task(self._调度())`，
每 60 秒检查一次今天有没有到点的档期，`terminate()` 里取消。

指令只是手动触发与查状态，业务逻辑全在 `_跑一轮` 里，两边共用。

三条容易改坏的地方：

- **档期过期不补跑。** 超过十分钟的档期直接丢弃。容器重启会把攒下的几轮
  一起放出来，看起来像刷屏。
- **发评论失败不重试。** 失败就跳过这一轮，重试只发生在「换关键词重搜」。
  同一轮重发只会让风控更早来。
- **`取排期` 用 `None` 和 `[]` 区分「今天还没排」与「今天排了零轮」。**
  合并成空列表会导致每分钟重排一次、每次都写盘。

## 选片不能用 pubdate

2026-10-21 实测，B站搜索五个排序值的播放量分布见 README 的表。`pubdate`
返回的全是刚上传、播放还是 0 的片子，过不了 `min_play`。只有 `totalrank`
能同时给出「播放量跨度大 + 有近期内容」。

改动选片逻辑前先跑 `uv run python test/verify_search.py`，确认接口还认
`totalrank`。

## @ 是怎么发出去的

不是接口参数，是正文文本。评论接口 `x/v2/reply/add` 的 data 只有
`oid / type / message / csrf`，服务端自己解析 `message` 里的 `@昵称`。

所以昵称必须一字不差；带空格的昵称解析可能断在空格处。

## 模型调用

`_问模型` 直连 provider 的 `text_chat()`，不用 `tool_loop_agent`：这里只需要
「一段文字换一段文字」，一个工具都不需要，而 `tool_loop_agent` 会把当前会话
挂着的全部工具 schema 塞进请求再走 runner 循环。

`recent_bili_critics` 是唯一注册的 LLM 工具，只读历史记录。

## config 为什么必须可省

AstrBot 的 `star_manager` 这样注入配置：

```python
if plugin_config and metadata.star_cls_type:
    star = metadata.star_cls_type(context=context, config=plugin_config)
else:
    star = metadata.star_cls_type(context=context)
```

仓库没有 `_conf_schema.json` 时第一个分支不走，于是只传 `context`。
`__init__` 里把 `config` 声明成必需参数会直接 `TypeError`，插件整个加载不起来。
