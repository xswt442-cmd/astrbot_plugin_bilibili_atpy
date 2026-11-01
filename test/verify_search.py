"""打真实接口验证 B站搜索还能用、字段还在。

不需要登录态：搜索走匿名请求，WBI 密钥从 nav 接口现取。所以这个脚本能进
定时 CI，验的是「接口还在、字段没改名、排序值还认」——单测里用构造数据
钉不住这些。

跑法：

    uv run python test/verify_search.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from atpy.bili import ApiError, BiliClient  # noqa: E402

REQUIRED_FIELDS = ("aid", "bvid", "标题", "up主", "播放", "发布")


async def main() -> int:
    client = BiliClient("", "")
    async with aiohttp.ClientSession() as session:
        try:
            results = await client.search_videos(session, "离谱", count=30, order="totalrank")
        except (ApiError, aiohttp.ClientError) as err:
            print(f"搜索接口失败：{type(err).__name__} {err}")
            return 1

    if not results:
        print("搜索返回 0 条。接口可能改了排序值，或者整个搜索下线了。")
        return 1

    missing = [
        item for item in results if any(item.get(key) in (None, "") for key in REQUIRED_FIELDS)
    ]
    if missing:
        print(f"{len(missing)} 条结果缺字段，第一条：{missing[0]}")
        return 1

    plays = sorted(item["播放"] for item in results)
    with_plays = [value for value in plays if value > 0]
    if not with_plays:
        # totalrank 全返回 0 播放，说明这个排序值已经不被认，退回成别的排序了。
        print("所有结果播放量都是 0，totalrank 可能已失效。")
        return 1

    newest = max(item["发布"] for item in results)
    age_days = (time.time() - newest) / 86400
    print(f"{len(results)} 条结果，播放 {plays[0]}-{plays[-1]}，最新一条 {age_days:.0f} 天前")

    if age_days > 400:
        print("最新一条也超过一年，搜索结果整体过时，接口可能出问题。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
