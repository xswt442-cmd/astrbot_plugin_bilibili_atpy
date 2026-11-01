"""把视频信息拼成提示词，再把模型输出洗成一句不超过十个字的锐评。

模型经常不听话：带引号、加「锐评：」前缀、写成两行、一口气甩三十个字。
清洗比提示词可靠，所以两处都要做。
"""

from __future__ import annotations

import re
from typing import Any

MAX_LENGTH = 10

SYSTEM_PROMPT = (
    "你是一个在评论区混了很久的老网友，说话又损又快。"
    "给你一个视频，你只写一句点评。"
    "要求：不超过十个汉字；不解释、不铺垫、不加引号；"
    "可以阴阳、可以震惊、可以装懂；"
    "不要写「这个视频」这类废话，直接说事。"
    "只输出这一句，不要任何前缀和后缀。"
)

_PREFIX_RE = re.compile(r"^(锐评|评论|点评|吐槽)\s*[:：]?\s*")
_QUOTES = "「」『』“”\"'‘’《》【】"


def build_prompt(video: dict[str, Any]) -> str:
    parts = [
        f"标题：{video.get('标题', '')}",
        f"UP主：{video.get('up主', '')}",
        f"分区：{video.get('分区', '')}",
        f"播放：{video.get('播放', 0)}",
    ]
    description = (video.get("简介") or "").strip()
    if description:
        parts.append(f"简介：{description[:150]}")
    parts.append("写一句点评。")
    return "\n".join(parts)


def clean(raw: str) -> str:
    """去前缀、去引号、取第一行，最后按字数截断。"""
    text = (raw or "").strip()
    if not text:
        return ""
    # 模型爱把结果塞进代码块或整段解释里，先取第一行有内容的。
    for line in text.splitlines():
        line = line.strip()
        if line:
            text = line
            break
    text = _PREFIX_RE.sub("", text)
    text = text.strip().strip(_QUOTES).strip()
    text = text.strip(_QUOTES).strip()
    # 中文按字符数算，一个汉字一个字。
    return text[:MAX_LENGTH].strip()


def is_usable(text: str) -> bool:
    return bool(text) and len(text) >= 2
