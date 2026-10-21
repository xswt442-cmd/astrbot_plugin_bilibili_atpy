"""指令组接线：`main.py` 里注册的子命令与 `atpy/兜底.子命令名` 必须对得上。

兜底的判据是「参数不以任何子命令开头就算落空」。两边一旦不同步：

- 兜底里少一个 → 用户打那个子命令时被判落空，`stop_event()` 掐掉，指令没反应
- 兜底里多一个 → 用户打一个不存在的子命令，没人接住，消息进模型让它瞎编

这不是形式一致，是两种都能复现的故障，所以用测试钉住。
"""

from __future__ import annotations

import re
from pathlib import Path

from atpy.兜底 import 子命令名

仓库根 = Path(__file__).resolve().parent.parent
_main = (仓库根 / "main.py").read_text(encoding="utf-8")

_子命令 = re.compile(r'@atpy\.command\(\s*"([^"]+)"(?:\s*,\s*alias=\{([^}]*)\})?\s*\)')


def _注册的全部名字() -> set[str]:
    名字: set[str] = set()
    for 匹配 in _子命令.finditer(_main):
        名字.add(匹配.group(1))
        if 匹配.group(2):
            名字.update(re.findall(r'"([^"]+)"', 匹配.group(2)))
    return 名字


def test_main里确实注册了子命令():
    名字 = _注册的全部名字()
    assert 名字, "main.py 里一个 @atpy.command 都没找到，写法变了就更新这个正则"


def test_兜底不多不少():
    注册的 = _注册的全部名字()
    assert 注册的 == set(子命令名), f"main.py 注册了 {sorted(注册的)}，兜底里是 {sorted(子命令名)}"


def test_指令组挂了兜底过滤器():
    """.filter 的返回值语义是「这条消息我管不管」，不是「命中没有」。"""
    assert "@custom_filter(_落空兜底)" in _main
    assert "@command_group(_组名, alias=_组别名)" in _main


def test_组别名带斜杠():
    """QQ 官方 At 唤醒不剥 message_str 里的 `/`，没有别名整条指令静默失败。"""
    assert '_组别名 = {f"/{_组名}"}' in _main, "main.py 里的 _组别名 必须带斜杠"
