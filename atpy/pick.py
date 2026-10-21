"""从搜索结果里挑一个值得锐评的视频。

挑片不看"好不好看"，只看"够不够怪"：播放量太低是没人看的废片，太高是
全网都刷过的烂梗。所以两头都卡，只在中间那段随机取。
"""

from __future__ import annotations

import random
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# 关键词池。分三组是为了每轮都能换一种"怪法"，而不是连续刷到同一类内容。
关键词池 = {
    "猎奇": [
        "离谱",
        "迷惑行为",
        "抽象",
        "野生",
        "人类早期",
        "这也能",
        "神操作",
        "奇葩",
        "祖传",
        "奇怪的挑战",
    ],
    "搞笑": [
        "整活",
        "沙雕",
        "名场面",
        "翻车",
        "魔性",
        "鬼畜",
        "笑到窒息",
        "离谱失败",
        "社死现场",
    ],
    "神秘": [
        "未解之谜",
        "诡异",
        "深海",
        "冷知识",
        "奇怪的知识",
        "神秘现象",
        "诡异录像",
        "深夜怪谈",
    ],
    "奇怪": [
        "奇怪的食物",
        "奇怪发明",
        "野生技术",
        "手搓",
        "野生手工",
        "离谱测评",
        "奇怪实验",
    ],
}


@dataclass(frozen=True)
class 门槛:
    最少播放: int
    最多播放: int
    最多几天前: int
    最短标题: int = 6


# 搜索词再怪也会捞到这几类东西：前一组评一句就等着被举报，后一组是
# `totalrank` 排序下混得很凶的网文与短剧推广——标题里塞满"练气""赘婿"
# "横行天下"，点进去是几分钟的读书广告，锐评它没有任何意义。
标题禁忌 = (
    "代孕",
    "赌博",
    "博彩",
    "约炮",
    "加微信",
    "私加",
    "引流",
    "刷单",
    "练气",
    "筑基",
    "仙帝",
    "仙尊",
    "赘婿",
    "龙王",
    "大夏",
    "横行天下",
    "打遍",
    "无敌手",
    "穿越成",
    "重生之",
    "全文完结",
)

# 光靠词表挡不住短剧：标题会写成「xxx 第1-55集 超清中字（全）」，
# 前缀千变万化，能认的只有集数格式和那几句固定后缀。
标题禁忌式 = (
    re.compile(r"第\s*\d+\s*[-~—至]\s*\d+\s*集"),
    re.compile(r"第\s*\d+\s*集\s*全"),
    re.compile(r"超清中字"),
    re.compile(r"1\s*[-~—]\s*\d+\s*集全"),
    # AI 剧集用 EP01 这种写法，逃过上面几条。
    re.compile(r"EP\s*\d+", re.IGNORECASE),
)


def 抽关键词(随机源: random.Random, 自定义: Iterable[str] = ()) -> str:
    """配了自定义词就只用那些，否则先摇一种怪法再从那一组里取一个。"""
    自定义表 = [词.strip() for 词 in 自定义 if 词.strip()]
    if 自定义表:
        return 随机源.choice(自定义表)
    分组 = 随机源.choice(list(关键词池))
    return 随机源.choice(关键词池[分组])


def 过滤(
    候选: list[dict[str, Any]],
    关: 门槛,
    已发过: set[str],
    现在: float | None = None,
) -> list[dict[str, Any]]:
    """留下播放量适中、时间够新、没发过、标题够长的。"""
    当下 = 现在 if 现在 is not None else time.time()
    最早 = 当下 - 关.最多几天前 * 86400
    留下 = []
    for 视频 in 候选:
        if not 视频.get("bvid") or not 视频.get("aid"):
            continue
        if 视频["bvid"] in 已发过:
            continue
        标题 = 视频.get("标题", "")
        if len(标题) < 关.最短标题:
            continue
        if any(词 in 标题 for 词 in 标题禁忌):
            continue
        if any(式.search(标题) for 式 in 标题禁忌式):
            continue
        播放 = 视频.get("播放") or 0
        if not (关.最少播放 <= 播放 <= 关.最多播放):
            continue
        发布 = 视频.get("发布") or 0
        if 发布 and 发布 < 最早:
            continue
        留下.append(视频)
    return 留下


def 挑一个(
    随机源: random.Random,
    候选: list[dict[str, Any]],
    已发过: set[str],
    关: 门槛,
) -> dict[str, Any] | None:
    """把筛选后的候选随机取一个。空列表返回 None，由调用方决定换词重搜。"""
    留下 = 过滤(候选, 关, 已发过)
    if not 留下:
        return None
    # 越怪越好：优先取播放量偏中位的那批，避免一眼就是爆款。
    留下.sort(key=lambda 视频: 视频.get("播放") or 0)
    偏冷 = 留下[: max(1, len(留下) // 2)]
    return 随机源.choice(偏冷)
