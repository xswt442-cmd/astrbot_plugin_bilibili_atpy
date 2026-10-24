"""从搜索结果里挑一个值得锐评的视频。

挑片不看好不好看，只看够不够怪：播放量太低是没人看的废片，太高是全网刷过的
烂梗，两头都卡。五类内容按日期轮着来，每天一类。
"""

from __future__ import annotations

import random
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

# 五类内容，每天轮一类。类别顺序就是轮转顺序，加类别会打乱节奏。
关键词池 = {
    "搞笑搞怪": [
        "整活",
        "沙雕",
        "鬼畜",
        "抽象",
        "笑死",
        "翻车现场",
        "社死",
        "离谱操作",
    ],
    "莫名其妙": [
        "迷惑行为",
        "人类迷惑行为",
        "不明所以",
        "脑回路",
        "莫名其妙",
        "精神污染",
        "这也能播",
    ],
    "二游": [
        "原神",
        "崩坏星穹铁道",
        "绝区零",
        "鸣潮",
        "明日方舟终末地",
        "二游抽卡",
        "米哈游",
    ],
    "王者荣耀": [
        "王者荣耀",
        "王者峡谷",
        "KPL",
        "五杀",
        "上分",
    ],
    "无畏契约": [
        "无畏契约",
        "瓦罗兰特",
        "Valorant",
        "爆头",
        "残局",
    ],
}


@dataclass(frozen=True)
class 门槛:
    最少播放: int
    最多播放: int
    # 0 表示不限天数。老视频也能评，评论区凉了无所谓，朋友是点进去看的。
    最多几天前: int = 0
    最短标题: int = 6


# 搜索词再怪也会捞到这两类东西。前一组评一句就等着被举报；后一组是
# `totalrank` 下混得很凶的网文与短剧推广——点进去是读书广告，锐评它没有意义。
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

# 词表挡不住短剧：标题写成「xxx 第1-55集 超清中字（全）」，前缀千变万化，
# 能认的只有集数格式和那几句固定后缀。
标题禁忌式 = (
    re.compile(r"第\s*\d+\s*[-~—至]\s*\d+\s*集"),
    re.compile(r"第\s*\d+\s*集\s*全"),
    re.compile(r"超清中字"),
    re.compile(r"1\s*[-~—]\s*\d+\s*集全"),
    # AI 剧集用 EP01 这种写法，逃过上面几条。
    re.compile(r"EP\s*\d+", re.IGNORECASE),
)


def 按天取类别(当天: date) -> str:
    """每天轮一个类别。用日期序数取模，不依赖历史记录，重启补跑都不会乱序。"""
    类别们 = list(关键词池)
    return 类别们[当天.toordinal() % len(类别们)]


def 抽关键词(随机源: random.Random, 自定义: Iterable[str] = (), 类别: str | None = None) -> str:
    """从指定类别里抽一个词。配了自定义词就只用那些——用户明确写了要搜什么。"""
    自定义表 = [词.strip() for 词 in 自定义 if 词.strip()]
    if 自定义表:
        return 随机源.choice(自定义表)
    if 类别 and 类别 in 关键词池:
        return 随机源.choice(关键词池[类别])
    return 随机源.choice(关键词池[随机源.choice(list(关键词池))])


def 过滤(
    候选: list[dict[str, Any]],
    关: 门槛,
    已发过: set[str],
    现在: float | None = None,
) -> list[dict[str, Any]]:
    """留下播放量在区间内、标题够长、没发过的。`最多几天前` 为 0 时不管时间。"""
    当下 = 现在 if 现在 is not None else time.time()
    最早 = 当下 - 关.最多几天前 * 86400 if 关.最多几天前 > 0 else 0
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
        if 最早:
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
