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
KEYWORD_POOL = {
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
class Threshold:
    min_play: int
    max_play: int
    # 0 表示不限天数。老视频也能评，评论区凉了无所谓，朋友是点进去看的。
    max_days_old: int = 0
    min_title_length: int = 6


# 搜索词再怪也会捞到这两类东西。前一组评一句就等着被举报；后一组是
# `totalrank` 下混得很凶的网文与短剧推广——点进去是读书广告，锐评它没有意义。
FORBIDDEN_TITLES = (
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
FORBIDDEN_TITLE_PATTERNS = (
    re.compile(r"第\s*\d+\s*[-~—至]\s*\d+\s*集"),
    re.compile(r"第\s*\d+\s*集\s*全"),
    re.compile(r"超清中字"),
    re.compile(r"1\s*[-~—]\s*\d+\s*集全"),
    # AI 剧集用 EP01 这种写法，逃过上面几条。
    re.compile(r"EP\s*\d+", re.IGNORECASE),
)


def category_for_date(day: date) -> str:
    """每天轮一个类别。用日期序数取模，不依赖历史记录，重启补跑都不会乱序。"""
    categories = list(KEYWORD_POOL)
    return categories[day.toordinal() % len(categories)]


def pick_keyword(
    rng: random.Random, custom: Iterable[str] = (), category: str | None = None
) -> str:
    """从指定类别里抽一个词。配了自定义词就只用那些——用户明确写了要搜什么。"""
    custom_words = [word.strip() for word in custom if word.strip()]
    if custom_words:
        return rng.choice(custom_words)
    if category and category in KEYWORD_POOL:
        return rng.choice(KEYWORD_POOL[category])
    return rng.choice(KEYWORD_POOL[rng.choice(list(KEYWORD_POOL))])


def filter_candidates(
    candidates: list[dict[str, Any]],
    limits: Threshold,
    sent: set[str],
    now: float | None = None,
) -> list[dict[str, Any]]:
    """留下播放量在区间内、标题够长、没发过的。`最多几天前` 为 0 时不管时间。"""
    current = now if now is not None else time.time()
    earliest = current - limits.max_days_old * 86400 if limits.max_days_old > 0 else 0
    kept = []
    for video in candidates:
        if not video.get("bvid") or not video.get("aid"):
            continue
        if video["bvid"] in sent:
            continue
        title = video.get("标题", "")
        if len(title) < limits.min_title_length:
            continue
        if any(word in title for word in FORBIDDEN_TITLES):
            continue
        if any(pattern.search(title) for pattern in FORBIDDEN_TITLE_PATTERNS):
            continue
        plays = video.get("播放") or 0
        if not (limits.min_play <= plays <= limits.max_play):
            continue
        if earliest:
            published = video.get("发布") or 0
            if published and published < earliest:
                continue
        kept.append(video)
    return kept


def pick_one(
    rng: random.Random,
    candidates: list[dict[str, Any]],
    sent: set[str],
    limits: Threshold,
) -> dict[str, Any] | None:
    """把筛选后的候选随机取一个。空列表返回 None，由调用方决定换词重搜。"""
    kept = filter_candidates(candidates, limits, sent)
    if not kept:
        return None
    # 越怪越好：优先取播放量偏中位的那批，避免一眼就是爆款。
    kept.sort(key=lambda video: video.get("播放") or 0)
    cooler = kept[: max(1, len(kept) // 2)]
    return rng.choice(cooler)
