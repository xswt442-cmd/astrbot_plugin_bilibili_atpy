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

from atpy.bili import B站客户端, 接口错误  # noqa: E402

必需字段 = ("aid", "bvid", "标题", "up主", "播放", "发布")


async def 主() -> int:
    客户端 = B站客户端("", "")
    async with aiohttp.ClientSession() as 会话:
        try:
            结果 = await 客户端.搜索视频(会话, "离谱", 条数=30, 排序="totalrank")
        except (接口错误, aiohttp.ClientError) as 错:
            print(f"搜索接口失败：{type(错).__name__} {错}")
            return 1

    if not 结果:
        print("搜索返回 0 条。接口可能改了排序值，或者整个搜索下线了。")
        return 1

    缺字段 = [条 for 条 in 结果 if any(条.get(键) in (None, "") for 键 in 必需字段)]
    if 缺字段:
        print(f"{len(缺字段)} 条结果缺字段，第一条：{缺字段[0]}")
        return 1

    播放 = sorted(条["播放"] for 条 in 结果)
    有播放量 = [值 for 值 in 播放 if 值 > 0]
    if not 有播放量:
        # totalrank 全返回 0 播放，说明这个排序值已经不被认，退回成别的排序了。
        print("所有结果播放量都是 0，totalrank 可能已失效。")
        return 1

    最新 = max(条["发布"] for 条 in 结果)
    最近天数 = (time.time() - 最新) / 86400
    print(f"{len(结果)} 条结果，播放 {播放[0]}-{播放[-1]}，最新一条 {最近天数:.0f} 天前")

    if 最近天数 > 400:
        print("最新一条也超过一年，搜索结果整体过时，接口可能出问题。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(主()))
