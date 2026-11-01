"""依赖清单的约束。

AstrBot 安装插件时把 requirements.txt 喂给 pip，而 pip 装在同一环境里，
装的就是 AstrBot 核心自己的依赖。核心给这些包装了版本护栏：插件若要求一个
与核心不同的精确版本，护栏会拦下 pip，安装整体失败。

`uv export` 恰好会把每个包钉成 `==`，正是触发护栏的写法。所以这个文件
必须手写。这里把三条约束钉住：

1. 不能出现 `==` 精确钉版本
2. 直接依赖要与 pyproject.toml 的 dependencies 对得上
3. 不能是 uv export 的产物
"""

from __future__ import annotations

import re
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
requirements_path = repo_root / "requirements.txt"
declared_path = repo_root / "pyproject.toml"

# 只取真正写依赖的行，注释和空行不算。
_DEPENDENCY_RE = re.compile(r"^[A-Za-z0-9_.\-]+")

# 项目声明支持 3.10，而 tomllib 要 3.11，所以这里不引 tomllib，
# 只需要 dependencies 那一段的包名，正则读比解析 TOML 省事。
_DEPENDENCY_SECTION_RE = re.compile(r"^dependencies\s*=\s*\[(.*?)\]", re.MULTILINE | re.DOTALL)


def _read_requirements() -> list[str]:
    return [
        line.strip()
        for line in requirements_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _read_declared() -> list[str]:
    section = _DEPENDENCY_SECTION_RE.search(declared_path.read_text(encoding="utf-8"))
    assert section, "pyproject.toml 里找不到 dependencies"
    # 一行一项。不能按逗号切：版本范围里自带逗号（>=3.9,<5），切开会断。
    return [
        item.strip().strip(",").strip('"').strip("'")
        for item in section.group(1).splitlines()
        if item.strip().strip(",").strip('"').strip("'")
    ]


def test_no_exact_pins():
    """`==` 会和核心的版本护栏撞车，pip 动不了核心的包就装不上。"""
    pinned = [line for line in _read_requirements() if "==" in line]
    assert not pinned, f"requirements.txt 不能钉死版本，会和核心冲突：{pinned}"


def test_not_uv_export_artifact():
    assert "uv 自动生成" not in requirements_path.read_text(encoding="utf-8")


def test_direct_dependencies_match_pyproject():
    """两个文件各服务一头：pyproject 给本地 uv sync，本清单给 AstrBot 的 pip。"""
    requirement_names = {_DEPENDENCY_RE.match(line).group() for line in _read_requirements()}
    declared_names = {_DEPENDENCY_RE.match(line).group() for line in _read_declared()}
    assert requirement_names == declared_names, (
        f"两边不一致。requirements.txt: {sorted(requirement_names)}，"
        f"pyproject.toml: {sorted(declared_names)}"
    )


def test_version_bounds_present():
    """每一行都要有版本下界，否则 pip 可能把核心的包换成任意版本。"""
    for line in _read_requirements():
        assert re.search(r"[><=]+[0-9]", line), f"缺少版本约束：{line}"


def test_lower_bounds_not_looser_than_pyproject():
    """清单可以比 pyproject 更严，不能更松。更松会让 pip 去动核心的包。"""

    def _lower_bound(constraint: str) -> tuple[int, ...]:
        match = re.search(r">=\s*([0-9.]+)", constraint)
        return tuple(int(x) for x in match.group(1).split(".")) if match else ()

    requirements = {line.split(">")[0].split("<")[0].strip(): line for line in _read_requirements()}
    for declared in _read_declared():
        package, _, constraint = declared.partition(">")
        assert _lower_bound(requirements[package]) >= _lower_bound(constraint), (
            f"{package} 在 requirements.txt 里的下界比 pyproject.toml 松"
        )
