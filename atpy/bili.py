"""B站接口：搜索视频、读详情、发评论、点赞收藏。

只有写操作需要登录态；搜索和读详情带上同一个 Cookie，省一次鉴权。
网络请求一律走 aiohttp。
"""

from __future__ import annotations

import hashlib
import json
import time
from functools import reduce
from typing import Any

import aiohttp

用户代理 = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

导航接口 = "https://api.bilibili.com/x/web-interface/nav"
搜索接口 = "https://api.bilibili.com/x/web-interface/wbi/search/type"
详情接口 = "https://api.bilibili.com/x/web-interface/view"
发评论接口 = "https://api.bilibili.com/x/v2/reply/add"
点赞接口 = "https://api.bilibili.com/x/v2/view/like"
收藏夹列表接口 = "https://api.bilibili.com/x/v3/fav/folder/created/list-all"
收藏接口 = "https://api.bilibili.com/x/v3/fav/resource/deal"

# WBI 签名用的重排表，B站前端固定值。
混淆表 = [
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
]

# 发评论的返回码。只翻译会实际遇到的几个，其余原样带回给调用方判断。
评论错误码 = {
    -101: "登录态失效，需要重新扫码",
    -111: "csrf 校验失败，bili_jct 不对",
    -403: "被风控拦截，先停一天",
    12002: "该视频评论区已关闭",
    12015: "被风控拦截，先停一天",
    12025: "内容含敏感词",
    12051: "评论发送过于频繁",
}


class 接口错误(RuntimeError):
    """B站返回了非 0 的业务码，或者干脆没返回 JSON。"""


def 解析返回体(文本: str, 状态: int, 地址: str) -> dict[str, Any]:
    """把 HTTP 响应翻成字典，翻不动就抛 `接口错误`。

    风控命中时 B站回的是 HTML 而不是 JSON（412），直接 `.json()` 抛的
    `JSONDecodeError` 不是 `接口错误`，会一路冒到调用方把整轮打崩。
    所以状态码和解析失败都在这里收口，调用方只认 `接口错误` 一种。
    """
    if 状态 == 412:
        raise 接口错误("B站返回 412，触发风控。隔几小时再试，或换小号。")
    if 状态 != 200:
        raise 接口错误(f"{地址} 返回 HTTP {状态}")

    try:
        载荷 = json.loads(文本)
    except json.JSONDecodeError as 错:
        # 截一段原文，能看出是验证页还是别的，又不至于刷屏。
        raise 接口错误(f"{地址} 返回的不是 JSON：{文本[:80]!r}") from 错

    if not isinstance(载荷, dict):
        raise 接口错误(f"{地址} 返回体不是对象")
    return 载荷


class B站客户端:
    def __init__(self, sessdata: str, bili_jct: str) -> None:
        self._sessdata = sessdata.strip()
        self._bili_jct = bili_jct.strip()
        self._过期时间 = 0.0
        self._图片密钥 = ""
        self._子密钥 = ""
        # 点赞收藏要 mid 和默认收藏夹 id，取一次就够，跨轮复用。
        self._mid = 0
        self._收藏夹 = ""

    def _饼干(self) -> str:
        return f"SESSDATA={self._sessdata}; bili_jct={self._bili_jct}"

    def 有登录态(self) -> bool:
        return bool(self._sessdata and self._bili_jct)

    def _请求头(self) -> dict[str, str]:
        return {
            "User-Agent": 用户代理,
            "Referer": "https://www.bilibili.com/",
            "Cookie": self._饼干(),
        }

    async def _取(
        self,
        会话: aiohttp.ClientSession,
        地址: str,
        参数: dict[str, Any],
    ) -> dict[str, Any]:
        async with 会话.get(
            地址, params=参数, headers=self._请求头(), timeout=aiohttp.ClientTimeout(total=15)
        ) as 响应:
            状态 = 响应.status
            文本 = await 响应.text()
        return 解析返回体(文本, 状态, 地址)

    async def _签名(self, 会话: aiohttp.ClientSession, 参数: dict[str, Any]) -> dict[str, Any]:
        """给 wbi 接口补 wts 与 w_rid。密钥约一天一换，缓存 6 小时。"""
        if time.time() > self._过期时间:
            载荷 = await self._取(会话, 导航接口, {})
            图片 = ((载荷.get("data") or {}).get("wbi_img")) or {}
            图片链接 = 图片.get("img_url", "")
            子链接 = 图片.get("sub_url", "")
            if not 图片链接 or not 子链接:
                raise 接口错误("取不到 wbi 密钥，导航接口没返回 wbi_img")
            self._图片密钥 = 图片链接.rsplit("/", 1)[-1].split(".")[0]
            self._子密钥 = 子链接.rsplit("/", 1)[-1].split(".")[0]
            self._过期时间 = time.time() + 6 * 3600

        原始 = self._图片密钥 + self._子密钥
        混入密钥 = reduce(lambda 累积, 位: 累积 + 原始[位], 混淆表, "")[:32]
        参数 = dict(参数)
        参数["wts"] = int(time.time())
        排序后 = dict(sorted(参数.items()))
        待签 = "&".join(f"{键}={值}" for 键, 值 in 排序后.items())
        排序后["w_rid"] = hashlib.md5((待签 + 混入密钥).encode()).hexdigest()
        return 排序后

    async def 搜索视频(
        self,
        会话: aiohttp.ClientSession,
        关键词: str,
        条数: int = 20,
        排序: str = "pubdate",
    ) -> list[dict[str, Any]]:
        """按关键词搜视频。排序 pubdate 拿新发布的，totalrank 拿综合。"""
        参数 = await self._签名(
            会话,
            {
                "keyword": 关键词,
                "search_type": "video",
                "page": 1,
                "page_size": 条数,
                "order": 排序,
            },
        )
        载荷 = await self._取(会话, 搜索接口, 参数)
        if 载荷.get("code") == -352:
            # 密钥换了，丢缓存重签一次。
            self._过期时间 = 0.0
            参数 = await self._签名(
                会话,
                {
                    "keyword": 关键词,
                    "search_type": "video",
                    "page": 1,
                    "page_size": 条数,
                    "order": 排序,
                },
            )
            载荷 = await self._取(会话, 搜索接口, 参数)
        if 载荷.get("code") != 0:
            raise 接口错误(f"搜索失败 code={载荷.get('code')} {载荷.get('message', '')}")

        结果 = []
        for 条目 in (载荷.get("data") or {}).get("result") or []:
            # 标题里的关键词会被包成 <em>，去掉标签才能直接喂模型。
            标题 = 条目.get("title", "")
            for 标签 in ('<em class="keyword">', "</em>", "<em>", "<em class='keyword'>"):
                标题 = 标题.replace(标签, "")
            结果.append(
                {
                    "aid": 条目.get("aid") or 条目.get("id"),
                    "bvid": 条目.get("bvid", ""),
                    "标题": 标题.strip(),
                    "up主": 条目.get("author", ""),
                    "简介": (条目.get("description") or "").strip(),
                    "播放": 条目.get("play") or 0,
                    "弹幕": 条目.get("video_review") or 0,
                    "时长": 条目.get("duration", ""),
                    "发布": 条目.get("pubdate") or 0,
                    "分区": 条目.get("typename", ""),
                }
            )
        return 结果

    async def 取详情(self, 会话: aiohttp.ClientSession, bvid: str) -> dict[str, Any] | None:
        载荷 = await self._取(会话, 详情接口, {"bvid": bvid})
        if 载荷.get("code") != 0:
            return None
        数据 = 载荷.get("data") or {}
        简介 = (数据.get("desc") or "").strip()
        return {
            "aid": 数据.get("aid"),
            "bvid": 数据.get("bvid", bvid),
            "标题": (数据.get("title") or "").strip(),
            "up主": ((数据.get("owner") or {}).get("name")) or "",
            "简介": 简介[:300],
            "播放": ((数据.get("stat") or {}).get("view")) or 0,
            "弹幕": ((数据.get("stat") or {}).get("danmaku")) or 0,
            "发布": 数据.get("pubdate") or 0,
            "分区": ((数据.get("tname")) or ""),
        }

    async def 发评论(
        self,
        会话: aiohttp.ClientSession,
        aid: int,
        内容: str,
    ) -> int:
        """在视频下发一条顶层评论，返回 rpid。"""
        async with 会话.post(
            发评论接口,
            data={
                "oid": aid,
                "type": 1,
                "message": 内容,
                "csrf": self._bili_jct,
                "plat": 1,
            },
            headers=self._请求头(),
            timeout=aiohttp.ClientTimeout(total=20),
        ) as 响应:
            载荷 = await 响应.json(content_type=None)
        if not isinstance(载荷, dict):
            raise 接口错误(f"发评论返回体不是对象：{响应.status}")
        码 = 载荷.get("code")
        if 码 != 0:
            原因 = 评论错误码.get(码) or 载荷.get("message") or "未知原因"
            raise 接口错误(f"发评论失败 code={码}：{原因}")
        return int(((载荷.get("data") or {}).get("rpid")) or 0)

    async def _提交(
        self,
        会话: aiohttp.ClientSession,
        地址: str,
        数据: dict[str, Any],
        说明: str,
    ) -> dict[str, Any]:
        """带 csrf 的写操作。非 0 业务码一律翻成 `接口错误`。"""
        async with 会话.post(
            地址,
            data={**数据, "csrf": self._bili_jct},
            headers=self._请求头(),
            timeout=aiohttp.ClientTimeout(total=15),
        ) as 响应:
            状态 = 响应.status
            文本 = await 响应.text()
        载荷 = 解析返回体(文本, 状态, 地址)
        码 = 载荷.get("code")
        if 码 != 0:
            raise 接口错误(f"{说明}失败 code={码}：{载荷.get('message') or '未知原因'}")
        return 载荷

    async def _我的mid(self, 会话: aiohttp.ClientSession) -> int:
        if self._mid:
            return self._mid
        载荷 = await self._取(会话, 导航接口, {})
        mid = (载荷.get("data") or {}).get("mid")
        if not mid:
            raise 接口错误("登录态失效，导航接口没返回 mid")
        self._mid = int(mid)
        return self._mid

    async def _默认收藏夹(self, 会话: aiohttp.ClientSession) -> str:
        """取账号下第一个收藏夹。列表按创建时间排，第一个就是默认的。"""
        if self._收藏夹:
            return self._收藏夹
        载荷 = await self._取(会话, 收藏夹列表接口, {"up_mid": await self._我的mid(会话)})
        列表 = (载荷.get("data") or {}).get("list") or []
        if not 列表:
            raise 接口错误("账号下没有收藏夹，建一个再试")
        self._收藏夹 = str(列表[0]["id"])
        return self._收藏夹

    async def 点赞(self, 会话: aiohttp.ClientSession, aid: int) -> None:
        await self._提交(会话, 点赞接口, {"aid": aid, "like": 1}, "点赞")

    async def 收藏(self, 会话: aiohttp.ClientSession, aid: int) -> None:
        await self._提交(
            会话,
            收藏接口,
            {"rid": aid, "type": 2, "add_media_ids": await self._默认收藏夹(会话)},
            "收藏",
        )
