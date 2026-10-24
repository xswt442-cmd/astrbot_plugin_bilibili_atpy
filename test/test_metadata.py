"""metadata.yaml 的约定。

AstrBot 从这份文件读插件信息，版本号也在里面。字段填错不影响加载，
但插件列表会显示成 `[MISSING: ...]`。
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

仓库根 = Path(__file__).resolve().parent.parent
元数据路径 = 仓库根 / "metadata.yaml"
声明路径 = 仓库根 / "pyproject.toml"

# 项目声明支持 3.10，tomllib 要 3.11，所以用正则读那一行，不引 tomllib。
_版本行 = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)
_lock版本行 = re.compile(
    r'name = "astrbot-plugin-bilibili-atpy"\nversion = "([^"]+)"', re.MULTILINE
)


def _元数据() -> str:
    return 元数据路径.read_text(encoding="utf-8")


def _元数据版本() -> str:
    匹配 = re.search(r"^version:\s*(\S+)", _元数据(), re.MULTILINE)
    assert 匹配, "metadata.yaml 里找不到 version"
    return 匹配.group(1)


def _声明版本() -> str:
    匹配 = _版本行.search(声明路径.read_text(encoding="utf-8"))
    assert 匹配, "pyproject.toml 里找不到 version"
    return 匹配.group(1)


def _lock版本() -> str:
    文本 = (仓库根 / "uv.lock").read_text(encoding="utf-8")
    匹配 = _lock版本行.search(文本)
    assert 匹配, "uv.lock 里找不到本项目的版本"
    return 匹配.group(1)


def test_三处版本号一致():
    """metadata 是 AstrBot 读的，pyproject 与 uv.lock 是本地与打包用的。

    对不上时本地构建出的版本号和插件里显示的不一样。
    """
    声明 = _声明版本()
    assert _元数据版本() == f"v{声明}"
    assert _lock版本() == 声明


def test_必需的字段都在():
    文本 = _元数据()
    for 字段 in ("name:", "display_name:", "short_desc:", "desc:", "version:", "author:"):
        assert 字段 in 文本, f"metadata.yaml 缺 {字段}"


def test_分类是市场自己定的那几个():
    """填错不影响安装，只是详情页的分类标签不对。"""
    匹配 = re.search(r"^category:\s*(\S+)", _元数据(), re.MULTILINE)
    assert 匹配, "metadata.yaml 里找不到 category"
    assert 匹配.group(1) == "娱乐"


def test_声明的AstrBot版本区间合理():
    匹配 = re.search(r'astrbot_version:\s*"?([^"\n]+)"?', _元数据())
    assert 匹配, "metadata.yaml 里找不到 astrbot_version"

    区间 = 匹配.group(1).strip()
    assert 区间.startswith(">="), f"下界写成了 {区间}"
    assert "<" in 区间, f"少了上界，升级 AstrBot 后会静默失效：{区间}"


def test_仓库名与插件名一致():
    """插件名要跟目录名一致，AstrBot 按目录名加载、按 name 字段识别。"""
    匹配 = re.search(r"^name:\s*(\S+)", _元数据(), re.MULTILINE)
    assert 匹配
    assert 匹配.group(1) == 仓库根.name, f"name 是 {匹配.group(1)}，目录是 {仓库根.name}"


def _png尺寸(路径: Path) -> tuple[int, int]:
    """读 PNG 头里的宽高。只为校验图标规格，不值得引 Pillow。"""
    头 = 路径.read_bytes()[:24]
    return struct.unpack(">II", 头[16:24])


def test_有图标且尺寸跟另外几个插件一致():
    """插件市场拿仓库根的 `logo.png` 当图标，没有就是灰底占位。

    另外三个插件都是 256×256，尺寸不一致在市场列表里会被拉伸。
    """
    图标 = 仓库根 / "logo.png"
    assert 图标.exists(), "缺 logo.png，市场上会显示成灰色占位"
    assert _png尺寸(图标) == (256, 256), f"logo.png 是 {_png尺寸(图标)}，应为 256×256"


def test_显示名与指令组名一致():
    """显示名改了但指令组没改，用户会照显示名去敲指令，然后没反应。"""
    文本 = (仓库根 / "main.py").read_text(encoding="utf-8")
    组名 = re.search(r'^_组名 = "([^"]+)"', 文本, re.MULTILINE)
    assert 组名, "main.py 里找不到 _组名"

    显示 = re.search(r"^display_name:\s*(\S+)", _元数据(), re.MULTILINE)
    assert 显示, "metadata.yaml 里找不到 display_name"

    assert 组名.group(1) == 显示.group(1), f"指令是 /{组名.group(1)}，显示名是 {显示.group(1)}"
