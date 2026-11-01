"""metadata.yaml 的约定。

AstrBot 从这份文件读插件信息，版本号也在里面。字段填错不影响加载，
但插件列表会显示成 `[MISSING: ...]`。
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
metadata_path = repo_root / "metadata.yaml"
declared_path = repo_root / "pyproject.toml"

# 项目声明支持 3.10，tomllib 要 3.11，所以用正则读那一行，不引 tomllib。
_VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)
_LOCK_VERSION_RE = re.compile(
    r'name = "astrbot-plugin-bilibili-atpy"\nversion = "([^"]+)"', re.MULTILINE
)


def _metadata() -> str:
    return metadata_path.read_text(encoding="utf-8")


def _metadata_version() -> str:
    match = re.search(r"^version:\s*(\S+)", _metadata(), re.MULTILINE)
    assert match, "metadata.yaml 里找不到 version"
    return match.group(1)


def _declared_version() -> str:
    match = _VERSION_RE.search(declared_path.read_text(encoding="utf-8"))
    assert match, "pyproject.toml 里找不到 version"
    return match.group(1)


def _lock_version() -> str:
    text = (repo_root / "uv.lock").read_text(encoding="utf-8")
    match = _LOCK_VERSION_RE.search(text)
    assert match, "uv.lock 里找不到本项目的版本"
    return match.group(1)


def test_version_consistent_in_three_files():
    """metadata 是 AstrBot 读的，pyproject 与 uv.lock 是本地与打包用的。

    对不上时本地构建出的版本号和插件里显示的不一样。
    """
    declared = _declared_version()
    assert _metadata_version() == f"v{declared}"
    assert _lock_version() == declared


def test_required_fields_present():
    text = _metadata()
    for field in ("name:", "display_name:", "short_desc:", "desc:", "version:", "author:"):
        assert field in text, f"metadata.yaml 缺 {field}"


def test_category_matches_market():
    """填错不影响安装，只是详情页的分类标签不对。"""
    match = re.search(r"^category:\s*(\S+)", _metadata(), re.MULTILINE)
    assert match, "metadata.yaml 里找不到 category"
    assert match.group(1) == "娱乐"


def test_astrbot_version_range_reasonable():
    match = re.search(r'astrbot_version:\s*"?([^"\n]+)"?', _metadata())
    assert match, "metadata.yaml 里找不到 astrbot_version"

    version_range = match.group(1).strip()
    assert version_range.startswith(">="), f"下界写成了 {version_range}"
    assert "<" in version_range, f"少了上界，升级 AstrBot 后会静默失效：{version_range}"


def test_repo_name_matches_plugin_name():
    """插件名要跟目录名一致，AstrBot 按目录名加载、按 name 字段识别。"""
    match = re.search(r"^name:\s*(\S+)", _metadata(), re.MULTILINE)
    assert match
    assert match.group(1) == repo_root.name, f"name 是 {match.group(1)}，目录是 {repo_root.name}"


def _png_size(path: Path) -> tuple[int, int]:
    """读 PNG 头里的宽高。只为校验图标规格，不值得引 Pillow。"""
    header = path.read_bytes()[:24]
    return struct.unpack(">II", header[16:24])


def test_logo_size_matches_other_plugins():
    """插件市场拿仓库根的 `logo.png` 当图标，没有就是灰底占位。

    另外三个插件都是 256×256，尺寸不一致在市场列表里会被拉伸。
    """
    icon = repo_root / "logo.png"
    assert icon.exists(), "缺 logo.png，市场上会显示成灰色占位"
    assert _png_size(icon) == (256, 256), f"logo.png 是 {_png_size(icon)}，应为 256×256"


def test_display_name_matches_command_group():
    """显示名改了但指令组没改，用户会照显示名去敲指令，然后没反应。"""
    text = (repo_root / "main.py").read_text(encoding="utf-8")
    group = re.search(r'^_GROUP = "([^"]+)"', text, re.MULTILINE)
    assert group, "main.py 里找不到 _GROUP"

    display = re.search(r"^display_name:\s*(\S+)", _metadata(), re.MULTILINE)
    assert display, "metadata.yaml 里找不到 display_name"

    assert group.group(1) == display.group(1), (
        f"指令是 /{group.group(1)}，显示名是 {display.group(1)}"
    )
