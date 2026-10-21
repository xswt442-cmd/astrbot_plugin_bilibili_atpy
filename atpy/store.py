"""落盘：发过什么、今天排在几点。

数据量很小（一天三五条），用两个 JSON 就够，不引数据库。
写入走临时文件再替换，避免容器被 kill 时留下半截文件。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

保留条数 = 200


def _读(路径: Path) -> dict[str, Any]:
    if not 路径.exists():
        return {}
    try:
        return json.loads(路径.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # 文件坏了不该让插件起不来：挪到旁边留证，按空处理。
        备份 = 路径.with_suffix(f".坏-{int(time.time())}.json")
        try:
            路径.replace(备份)
        except OSError:
            pass
        return {}


def _写(路径: Path, 内容: dict[str, Any]) -> None:
    路径.parent.mkdir(parents=True, exist_ok=True)
    临时 = 路径.with_suffix(".临时")
    临时.write_text(json.dumps(内容, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(临时, 路径)


class 记录簿:
    def __init__(self, 目录: Path) -> None:
        self._目录 = 目录
        self._历史路径 = 目录 / "history.json"
        self._排期路径 = 目录 / "plan.json"

    def 已发过的(self) -> set[str]:
        内容 = _读(self._历史路径)
        return {条.get("bvid", "") for 条 in 内容.get("记录", []) if 条.get("bvid")}

    def 全部(self) -> list[dict[str, Any]]:
        return list(_读(self._历史路径).get("记录", []))

    def 最近(self, 条数: int = 10) -> list[dict[str, Any]]:
        return self.全部()[-条数:][::-1]

    def 追加(self, 条目: dict[str, Any]) -> None:
        内容 = _读(self._历史路径)
        记录 = list(内容.get("记录", []))
        记录.append({**条目, "时间": 条目.get("时间") or int(time.time())})
        _写(self._历史路径, {"记录": 记录[-保留条数:]})

    def 取排期(self, 日期: str) -> list[int] | None:
        """还没给这一天排过时返回 None，排过但一轮都没有时返回空列表。"""
        内容 = _读(self._排期路径)
        if 内容.get("日期") != 日期:
            return None
        return [int(值) for 值 in 内容.get("时刻", [])]

    def 存排期(self, 日期: str, 时刻: list[int]) -> None:
        _写(self._排期路径, {"日期": 日期, "时刻": 时刻})
