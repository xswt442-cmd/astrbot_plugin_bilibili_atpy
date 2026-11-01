"""指令组接线：`main.py` 里注册的子命令与 `atpy/兜底.子命令名` 必须对得上。

兜底的判据是「参数不以任何子命令开头就算落空」。两边一旦不同步：

- 兜底里少一个 → 用户打那个子命令时被判落空，`stop_event()` 掐掉，指令没反应
- 兜底里多一个 → 用户打一个不存在的子命令，没人接住，消息进模型让它瞎编

这不是形式一致，是两种都能复现的故障，所以用测试钉住。
"""

from __future__ import annotations

import re
from pathlib import Path

from atpy.fallback import SUBCOMMANDS

repo_root = Path(__file__).resolve().parent.parent
_main = (repo_root / "main.py").read_text(encoding="utf-8")

_COMMAND_RE = re.compile(r'@atpy\.command\(\s*"([^"]+)"(?:\s*,\s*alias=\{([^}]*)\})?\s*\)')


def _registered_names() -> set[str]:
    names: set[str] = set()
    for match in _COMMAND_RE.finditer(_main):
        names.add(match.group(1))
        if match.group(2):
            names.update(re.findall(r'"([^"]+)"', match.group(2)))
    return names


def test_main_registers_commands():
    names = _registered_names()
    assert names, "main.py 里一个 @atpy.command 都没找到，写法变了就更新这个正则"


def test_fallback_matches_registered_commands():
    registered = _registered_names()
    assert registered == set(SUBCOMMANDS), (
        f"main.py 注册了 {sorted(registered)}，兜底里是 {sorted(SUBCOMMANDS)}"
    )


def test_group_has_fallback_filter():
    """.filter 的返回值语义是「这条消息我管不管」，不是「命中没有」。"""
    assert "@custom_filter(_MissFallbackFilter)" in _main
    assert "@command_group(_GROUP, alias=_GROUP_ALIASES)" in _main


def test_group_alias_includes_slash():
    """QQ 官方 At 唤醒不剥 message_str 里的 `/`，没有别名整条指令静默失败。"""
    assert '_GROUP_ALIASES = {f"/{_GROUP}"}' in _main, "main.py 里的 _GROUP_ALIASES 必须带斜杠"
