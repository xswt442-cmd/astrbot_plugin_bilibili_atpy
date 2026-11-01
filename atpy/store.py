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

MAX_KEPT = 200


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # 文件坏了不该让插件起不来：挪到旁边留证，按空处理。
        backup = path.with_suffix(f".坏-{int(time.time())}.json")
        try:
            path.replace(backup)
        except OSError:
            pass
        return {}


def _write(path: Path, content: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".临时")
    tmp.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class RecordBook:
    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._history_path = directory / "history.json"
        self._plan_path = directory / "plan.json"

    def sent_bvids(self) -> set[str]:
        content = _read(self._history_path)
        return {item.get("bvid", "") for item in content.get("记录", []) if item.get("bvid")}

    def all_records(self) -> list[dict[str, Any]]:
        return list(_read(self._history_path).get("记录", []))

    def recent(self, count: int = 10) -> list[dict[str, Any]]:
        return self.all_records()[-count:][::-1]

    def append(self, entry: dict[str, Any]) -> None:
        content = _read(self._history_path)
        records = list(content.get("记录", []))
        records.append({**entry, "时间": entry.get("时间") or int(time.time())})
        _write(self._history_path, {"记录": records[-MAX_KEPT:]})

    def get_schedule(self, date: str) -> list[int] | None:
        """还没给这一天排过时返回 None，排过但一轮都没有时返回空列表。"""
        content = _read(self._plan_path)
        if content.get("日期") != date:
            return None
        return [int(value) for value in content.get("时刻", [])]

    def set_schedule(self, date: str, slots: list[int]) -> None:
        _write(self._plan_path, {"日期": date, "时刻": slots})
