# 任务：把 `astrbot_plugin_bilibili_atpy` 的代码标识符全部改成英文

> 这条 prompt 直接交给执行方 agent。它是自包含的，不需要额外上下文。
> 仓库路径：`E:\.codes\bot\astrbot_plugin_bilibili_atpy`（Linux/WSL 下为 `/e/.codes/bot/astrbot_plugin_bilibili_atpy`）

---

## 0. 背景与目标

这个插件叫 `bilibili_atpy`（B 站自动锐评 @ 好友）。当前代码里大量使用中文作为
标识符（函数名、类名、变量名、参数名、常量名、测试用例名）。

同一批插件里的另外三个仓库（`astrbot_plugin_aiva`、`astrbot_plugin_ainong`、
`astrbot_plugin_aiwm`）已经完成了同样的改造，验证过可行、行为零变化。
**atpy 是最后一个，目标是与那三个仓库保持一致。**

当前基线（2026-11-02 实测）：

| 项目 | 现状 |
|---|---|
| 版本 | `v0.1.11`（`metadata.yaml` / `pyproject.toml` / `uv.lock` 三处一致） |
| 测试 | `62 passed` |
| 中文标识符 | 464 个（唯一名），分布在 16 个 `.py` 文件 |
| ruff | `uv run ruff check .` 干净，`uv run ruff format --check .` 干净 |

---

## 1. 核心规则

### 改成英文的（标识符）

- 函数名、类名、方法名
- 变量名、局部变量名
- 参数名（含关键字参数名 `foo=...` 的 `foo`）
- 模块级常量名
- 测试用例名（`test_xxx`）、测试类名（`TestXxx`）
- **模块文件名本身**——`atpy/兜底.py` → `atpy/fallback.py`

### 保持中文的（不是标识符）

- 注释、`docstring`
- 用户能看到的文案：提示文本、指令名、错误消息、帮助文本
- 指令名与组名：`/atpy 现在`、`/atpy 预览`、`/atpy 最近`、`/atpy 状态`、`/atpy 取UMO`、`/atpy 帮助`
- **磁盘上已经落盘的 JSON 键**——这是硬约束，见第 3 节
- `_conf_schema.json` 里的配置键（`enabled` / `sessdata` / `bili_jct` / `friends` /
  `notify_umo` / `rounds_min` / `rounds_max` / `min_play` / `max_play` /
  `max_days_old` / `dry_run` / `keywords` / `active_start_hour` / `active_end_hour` /
  `model_timeout_seconds` 等）——这些本来就是英文，保持原样

**判断标准很简单：Python 解析器把它当"名字"的，改；只是字符串内容的，不改。**

---

## 2. 仓库现状速览（省得你再摸一遍）

源码 6 个文件：

| 文件 | 行数 | 中文标识符 |
|---|---|---|
| `atpy/bili.py` | 352 | 63 |
| `atpy/pick.py` | 173 | 32 |
| `atpy/critic.py` | 60 | 13 |
| `atpy/store.py` | 70 | 25 |
| `atpy/兜底.py` | 94 | 14 |
| `main.py` | 468 | 124 |

测试 9 个文件：

```
test/test_critic.py          test/test_main_wiring.py
test/test_metadata.py        test/test_pick.py
test/test_requirements.py    test/test_store.py
test/test_兜底.py             test/test_解析返回体.py
test/verify_search.py
```

需要改名的文件（两个）：

- `atpy/兜底.py` → `atpy/fallback.py`
- `test/test_兜底.py` → `test/test_fallback.py`
- `test/test_解析返回体.py` → `test/test_parse_response.py`

`atpy/兜底.py` 当前的 `__all__`：

```python
__all__ = ["子命令名", "以组名开头", "取落空参数", "是否落空", "落空提示", "帮助文本"]
```

建议统一到另外三个仓库已定下的命名（**跨仓库一致是硬要求**）：

```python
__all__ = [
    "SUBCOMMANDS",
    "starts_with_group",
    "leftover_arg",
    "is_command_miss",
    "miss_hint",
    "help_text",
]
```

`main.py` 的兜底过滤器类：`_落空兜底` → `_MissFallbackFilter`。
`main.py` 的指令处理方法：`现在` / `预览` / `最近` / `状态` / `取UMO` / `帮助`
→ 保持中文（用户可见的指令名），但**方法名就是指令名**，所以它们必须保持中文，
不要改。这一点在别的仓库里是靠"指令处理函数叫 `xxx_cmd`"解决的，atpy 这里
沿用现状（指令名与方法名同形）即可，不要为了统一而把指令名改成英文。

其余跨仓库统一的命名（能套用的套用）：

- 存储类：`CredentialStore`（方法 `path_for` / `read` / `write` / `iter_all` /
  `find_by_nickname` / `delete`）——atpy 的 `atpy/store.py` 里对应的是 `记录簿`，
  改为 `RecordBook`；`_读` / `_写` → `_read` / `_write`
- 统计/提示词：`summarize` / `summary_text` / `contrast_points` / `contrast_text` /
  `advantage_count`；提示词常量 `TITLE_PREFIX` / `FLUFF_WORDS` / `SIMULATION_NOTICE`
- HTTP 客户端类：`B站客户端` → `BiliClient`；异常 `接口错误` → `ApiError`
- 落盘读取：`_文本(config, ...)` / `_整数(...)` / `_开关(...)` / `_拆分(...)`
  → `_text` / `_int` / `_flag` / `_split`

---

## 3. 磁盘 JSON 键：硬约束，不要动

`atpy/store.py` 往 `data/plugin_data/astrbot_plugin_bilibili_atpy/` 写两个文件，
里面的键**已经在用户机器上落盘了**，改了必须做数据迁移，因此**一律保持中文**：

- `history.json`：`记录`（数组）、`时间`、`bvid`
- `plan.json`：`日期`、`时刻`

也就是说，下面这种写法**保留原样**：

```python
内容.get("记录", [])      # ✅ 保留
记录.append({**条目, "时间": ...})   # ✅ 保留
```

但**围绕这些键的变量名**要改：`内容` → `content`、`记录` → `records`、
`条目` → `entry`、`时刻` → `slots`、`日期` → `date`。

> 同样地，`bili.py` 里从 B 站接口返回体读到的中文字段（如 `bvid`、`pic`、`title`、
> `play`、`like` 等）要看清楚是**接口字段**还是**我们自己的键**。B 站接口返回的
> 字段是外部契约，保持原样；我们自己在中间层造出来的键可以改。`test_解析返回体.py`
> 就是在测这块，改之前先读清楚。

---

## 4. 工作方法

### 4.1 逐模块推进，一次一个模块

顺序建议（依赖从下往上）：

```
atpy/store.py  →  atpy/critic.py  →  atpy/pick.py  →  atpy/bili.py
→  atpy/fallback.py（改名兜底.py）  →  main.py  →  test/*
```

每完成一个模块：

```bash
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run python -m pytest -q
```

**全绿才提交。** 提交信息用中文，格式 `refactor: <模块> 改用英文标识符`。

### 4.2 用 token 级改名工具，不要用正则

**绝对不要**用 `sed` / `str.replace` 全局替换中文标识符——那会连注释、字符串、
用户文案一起改掉，而且 `取` 这种单字会命中无数无关位置。

正确做法：用 `tokenize` 只替换 `NAME` 记号，字符串与注释原样保留。

工具已经写好，在 `E:\.codes\bot\.tmp-rename\`：

- `rename_names.py` — 单文件：`python rename_names.py <文件> <映射.json>`
- `rename_batch.py` — 批量：映射目录里每个 `xxx.json` 对应同路径的 `xxx` 文件

**如果那个路径在你那边不存在，把下面这段存成 `rename_names.py` 用即可**
（自包含，只依赖标准库）：

```python
"""按手写映射表重命名标识符：只替换 NAME 记号，字符串与注释不动。

用法：python rename_names.py <文件> <映射.json>
映射表必须逐文件手写，不做任何自动翻译——自动翻出来的名字没人看得懂。
"""

from __future__ import annotations

import io
import json
import sys
import tokenize
from pathlib import Path


def main() -> None:
    path = Path(sys.argv[1])
    mapping = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

    source = path.read_text(encoding="utf-8")
    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))

    edits: list[tuple[int, int, int, int, str]] = []
    for tok in tokens:
        if tok.type != tokenize.NAME:
            continue
        new = mapping.get(tok.string)
        if new is not None and new != tok.string:
            edits.append((*tok.start, *tok.end, new))

    lines = source.splitlines(keepends=True)
    for start_row, start_col, end_row, end_col, new in reversed(edits):
        assert start_row == end_row, f"跨行记号：{path}:{start_row}"
        line = lines[start_row - 1]
        lines[start_row - 1] = line[:start_col] + new + line[end_col:]

    path.write_text("".join(lines), encoding="utf-8", newline="")
    print(f"{path.name}: 改了 {len(edits)} 处")


if __name__ == "__main__":
    main()
```

### 4.3 映射表必须手写，逐文件手写

**不允许脚本自动生成映射表。** 机器猜不出 `取排期` 该叫 `get_schedule` 还是
`fetch_plan`——上一个仓库用自动翻译全量跑过一遍，结果是满仓库看不懂的变量名，
推倒重来了。

映射表格式（JSON）：

```json
{
  "记录簿": "RecordBook",
  "_读": "_read",
  "_写": "_write",
  "保留条数": "MAX_KEPT",
  "内容": "content"
}
```

同一批名字在多个文件里出现是正常的（`内容`、`数据`、`响应`），**每个文件各写一份
映射表**，不要共用一张全局表——不同文件里同一个中文词的英文译法经常不一样。

---

## 5. 五个必须知道的坑

这五个坑都是上一批仓库实际踩过的，全部踩一遍会浪费很多时间。

### 坑 1：改名会撞名（最隐蔽）

把 `响应` 改成 `response` 时，测试里 `def 响应()` 和局部变量 `响应` 会**同时**
变成 `response`，直接 `UnboundLocalError`。同理 `主源码 = 主源码.read_text()`。

- 撞名是**运行时**错误，ruff 和静态检查都查不出来
- **每改完一批必须立刻跑测试**，不要攒到最后
- 改完某个文件后如果报 `NameError` / `UnboundLocalError` / `AttributeError`，
  优先怀疑撞名

### 坑 2：`__all__` 是字符串，不是标识符

tokenize 工具只换 `NAME` 记号，`__all__ = ["子命令名", ...]` 里的中文**不会自动改**。

- 不手动改的话 ruff 报 `F822`（undefined name in `__all__`）
- 所有 `__all__` 都要手动同步

### 坑 3：`argparse` 的 `dest` 不跟选项名走

```python
parse.add_argument("--只看", ...)   # dest 自动变成 "只看"
parse.add_argument("--only", ...)   # dest 自动变成 "only"，不是 "only_check"
```

`test/verify_search.py` 如果有命令行参数，改名后要显式写：

```python
parse.add_argument("--only", dest="only_check", help="只探某个路径")
```

否则运行时报 `Namespace has no attribute 'only_check'`。

### 坑 4：`parametrize` 的 argname 也是字符串

```python
@pytest.mark.parametrize("消息", [...])          # ← 这个字符串是字面量
def test_xxx(self, 消息): ...
```

函数参数改名后，这里的 `"消息"` **不会自动改**，收集期直接报
`function uses no argument '消息'`。两个都要改。

### 坑 5：Git Bash 的路径转换

在 Git Bash 里跑 `--only /go/account/...` 这种以 `/` 开头的参数，Git 会把它
当路径转成 `C:/Program Files/Git/go/...`，看着像参数没生效。

```bash
MSYS_NO_PATHCONV=1 uv run python test/verify_search.py --only /xxx
```

**不是代码问题**，别去查代码。

---

## 6. 验收标准

全部满足才算完成：

### 6.1 零中文标识符

写个扫描脚本（用 `ast` 遍历，统计 `FunctionDef` / `AsyncFunctionDef` / `ClassDef`
/ `Name` / `arg` / `Attribute` / `keyword.arg`），结果必须是 **0**：

```bash
cd astrbot_plugin_bilibili_atpy
uv run python - <<'PY'
import ast, pathlib, re
汉 = re.compile(r"[\u4e00-\u9fff]")
n = 0
for p in sorted(pathlib.Path(".").rglob("*.py")):
    if ".venv" in p.parts:
        continue
    try:
        树 = ast.parse(p.read_text(encoding="utf-8"))
    except SyntaxError:
        continue
    for x in ast.walk(树):
        name = None
        if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = x.name
        elif isinstance(x, ast.Name):
            name = x.id
        elif isinstance(x, ast.arg):
            name = x.arg
        elif isinstance(x, ast.Attribute):
            name = x.attr
        elif isinstance(x, ast.keyword) and x.arg:
            name = x.arg
        if name and 汉.search(name):
            n += 1
            print(f"{p}:{x.lineno} {name}")
print("剩余中文标识符出现次数:", n)
PY
```

### 6.2 测试与静态检查

```bash
uv run ruff check .              # 0 error
uv run ruff format --check .     # All done
uv run python -m pytest -q       # 62 passed（数量可以变，但一条都不能少、一条都不能挂）
```

### 6.3 文档同步

`AGENTS.md` 里有大量旧名字，必须一起改：

- 结构清单里的 `atpy/兜底.py` → `atpy/fallback.py`
- 正文里的 `atpy/兜底.子命令名` → `atpy.fallback.SUBCOMMANDS`
- 正文里的 `_落空兜底` → `_MissFallbackFilter`
- 正文里的 `取排期` → `get_schedule`（或你实际用的名字）
- **补一条约定**，和另外三个仓库表述一致：

```markdown
- **标识符一律英文**（函数、类、变量、参数、常量、测试用例名），注释、docstring、
  提示文案、指令名与磁盘上的 JSON 键保持中文。`内容.get("记录", [])` 这类键是
  已落盘的数据，改动要迁移。
```

`CLAUDE.md` 如果也引用了旧名，一并改。

### 6.4 落盘数据兼容

改完之后，确认旧的 `history.json` / `plan.json` 还能被读：

- 第 3 节里那些中文键一个都没动，所以天然兼容
- 但要确认没有把读这些键的**变量名**顺手改成字面量，比如写成
  `content.get("记录")` 而不是 `content.get("记录")`（这个例子是对的）；
  要留意别把 `"记录"` 写成了 `"records"`——那会静默读到空数据

---

## 7. 发版与部署（做完改造后）

改造是纯重构，行为零变化。发版走仓库既有的流程，参照 `docs/RELEASING.md`。

### 7.1 版本号

- 当前 `v0.1.11` → 建议 **`v0.2.0`**（和另外三个仓库的版本线对齐）
- 三处都要改：`metadata.yaml`（`version: v0.2.0`）、`pyproject.toml`
  （`version = "0.2.0"`）、`uv.lock`（本项目那段的 `version = "0.2.0"`）
- `docs/CHANGELOG.md` 顶部加一节：

```markdown
## [0.2.0] - 2026-11-02

### 变更

- **代码标识符全部改成英文。** 函数、类、变量、参数、常量与测试用例名统一
  英文命名，注释、docstring、提示文案、指令名与磁盘上的 JSON 键保持中文。
  行为零变化，`test/` 全部用例照旧通过。模块文件也一并改名：
  `atpy/兜底.py` → `atpy/fallback.py` ——模块名同样是标识符。

### 说明

- `history.json` 的 `记录` / `时间` / `bvid`，`plan.json` 的 `日期` / `时刻`
  这些键**没有动**：它们是已经落盘的字段，改了就要给所有用户做迁移。
```

### 7.2 推送与 CI

```bash
cd astrbot_plugin_bilibili_atpy
export PATH="$PWD/.venv/Scripts:$PATH"
git push origin dev
git push origin dev:main
```

等 CI（`checks.yml`）**通过**再发 release：

```bash
gh workflow run release.yml -R xswt442-cmd/astrbot_plugin_bilibili_atpy \
  --ref main -f version=v0.2.0
```

### 7.3 部署到线上

参照另外三个仓库的做法（备份 → 解包覆盖 → 重启 → 看日志）：

```bash
P=/opt/qq-ai/astrbot-data/plugins
B=/opt/qq-ai/plugin-backups/20261102-020
sudo mkdir -p $B
sudo cp -a $P/astrbot_plugin_bilibili_atpy $B/astrbot_plugin_bilibili_atpy
sudo rm -rf $P/astrbot_plugin_bilibili_atpy
sudo tar -xzf /tmp/astrbot_plugin_bilibili_atpy.tgz -C $P
sudo grep -m1 '^version' $P/astrbot_plugin_bilibili_atpy/metadata.yaml
sudo docker restart astrbot
sleep 36
sudo docker logs --tail 400 astrbot 2>&1 | grep -E "Plugin astrbot_plugin_bilibili_atpy"
```

部署后确认：

- 日志里插件加载成功、版本是 `v0.2.0`
- 启动后该插件的 `ERRO` 条数为 0
- 容器内 `import atpy.fallback` 能通、旧路径 `atpy.兜底` 不存在
- 发一条 `/atpy 帮助` 确认指令组和帮助文本仍然正常

---

## 8. 交付报告

做完之后，用中文简要汇报：

1. 改了几个模块、几个文件、总共多少个中文标识符
2. 改名后的模块清单（`atpy/` 下的文件名）
3. `ruff` / `pytest` 的最终结果
4. 版本号、tag、Release、线上加载时间与日志检查结果
5. 保留中文的地方有哪些（分类说明：文案 / 指令名 / 落盘键）
6. 踩到的坑（如果有新的，值得记下来）
7. **哪些地方需要人工确认**（比如某个译名拿不准、某个键介于"接口字段"和"自有键"之间）

有拿不准的地方，**先问，不要猜着改**。
