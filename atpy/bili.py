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

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

NAV_API = "https://api.bilibili.com/x/web-interface/nav"
SEARCH_API = "https://api.bilibili.com/x/web-interface/wbi/search/type"
VIEW_API = "https://api.bilibili.com/x/web-interface/view"
REPLY_API = "https://api.bilibili.com/x/v2/reply/add"
LIKE_API = "https://api.bilibili.com/x/v2/view/like"
FAV_LIST_API = "https://api.bilibili.com/x/v3/fav/folder/created/list-all"
FAV_API = "https://api.bilibili.com/x/v3/fav/resource/deal"

# WBI 签名用的重排表，B站前端固定值。
MIXIN_TABLE = [
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
REPLY_ERROR_CODES = {
    -101: "登录态失效，需要重新扫码",
    -111: "csrf 校验失败，bili_jct 不对",
    -403: "被风控拦截，先停一天",
    12002: "该视频评论区已关闭",
    12015: "被风控拦截，先停一天",
    12025: "内容含敏感词",
    12051: "评论发送过于频繁",
}


class ApiError(RuntimeError):
    """B站返回了非 0 的业务码，或者干脆没返回 JSON。"""


def parse_response(text: str, status: int, url: str) -> dict[str, Any]:
    """把 HTTP 响应翻成字典，翻不动就抛 `接口错误`。

    风控命中时 B站回的是 HTML 而不是 JSON（412），直接 `.json()` 抛的
    `JSONDecodeError` 不是 `接口错误`，会一路冒到调用方把整轮打崩。
    所以状态码和解析失败都在这里收口，调用方只认 `接口错误` 一种。
    """
    if status == 412:
        raise ApiError("B站返回 412，触发风控。隔几小时再试，或换小号。")
    if status != 200:
        raise ApiError(f"{url} 返回 HTTP {status}")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as err:
        # 截一段原文，能看出是验证页还是别的，又不至于刷屏。
        raise ApiError(f"{url} 返回的不是 JSON：{text[:80]!r}") from err

    if not isinstance(payload, dict):
        raise ApiError(f"{url} 返回体不是对象")
    return payload


class BiliClient:
    def __init__(self, sessdata: str, bili_jct: str) -> None:
        self._sessdata = sessdata.strip()
        self._bili_jct = bili_jct.strip()
        self._expires_at = 0.0
        self._img_key = ""
        self._sub_key = ""
        # 点赞收藏要 mid 和默认收藏夹 id，取一次就够，跨轮复用。
        self._mid = 0
        self._fav_id = ""

    def _cookie(self) -> str:
        return f"SESSDATA={self._sessdata}; bili_jct={self._bili_jct}"

    def has_login(self) -> bool:
        return bool(self._sessdata and self._bili_jct)

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": USER_AGENT,
            "Referer": "https://www.bilibili.com/",
            "Cookie": self._cookie(),
        }

    async def _get(
        self,
        session: aiohttp.ClientSession,
        url: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        async with session.get(
            url, params=params, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=15)
        ) as response:
            status = response.status
            text = await response.text()
        return parse_response(text, status, url)

    async def _sign(self, session: aiohttp.ClientSession, params: dict[str, Any]) -> dict[str, Any]:
        """给 wbi 接口补 wts 与 w_rid。密钥约一天一换，缓存 6 小时。"""
        if time.time() > self._expires_at:
            payload = await self._get(session, NAV_API, {})
            img = ((payload.get("data") or {}).get("wbi_img")) or {}
            img_url = img.get("img_url", "")
            sub_url = img.get("sub_url", "")
            if not img_url or not sub_url:
                raise ApiError("取不到 wbi 密钥，导航接口没返回 wbi_img")
            self._img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
            self._sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
            self._expires_at = time.time() + 6 * 3600

        raw = self._img_key + self._sub_key
        mixin_key = reduce(lambda acc, idx: acc + raw[idx], MIXIN_TABLE, "")[:32]
        params = dict(params)
        params["wts"] = int(time.time())
        sorted_params = dict(sorted(params.items()))
        to_sign = "&".join(f"{key}={value}" for key, value in sorted_params.items())
        sorted_params["w_rid"] = hashlib.md5((to_sign + mixin_key).encode()).hexdigest()
        return sorted_params

    async def search_videos(
        self,
        session: aiohttp.ClientSession,
        keyword: str,
        count: int = 20,
        order: str = "pubdate",
    ) -> list[dict[str, Any]]:
        """按关键词搜视频。排序 pubdate 拿新发布的，totalrank 拿综合。"""
        params = await self._sign(
            session,
            {
                "keyword": keyword,
                "search_type": "video",
                "page": 1,
                "page_size": count,
                "order": order,
            },
        )
        payload = await self._get(session, SEARCH_API, params)
        if payload.get("code") == -352:
            # 密钥换了，丢缓存重签一次。
            self._expires_at = 0.0
            params = await self._sign(
                session,
                {
                    "keyword": keyword,
                    "search_type": "video",
                    "page": 1,
                    "page_size": count,
                    "order": order,
                },
            )
            payload = await self._get(session, SEARCH_API, params)
        if payload.get("code") != 0:
            raise ApiError(f"搜索失败 code={payload.get('code')} {payload.get('message', '')}")

        results = []
        for item in (payload.get("data") or {}).get("result") or []:
            # 标题里的关键词会被包成 <em>，去掉标签才能直接喂模型。
            title = item.get("title", "")
            for tag in ('<em class="keyword">', "</em>", "<em>", "<em class='keyword'>"):
                title = title.replace(tag, "")
            results.append(
                {
                    "aid": item.get("aid") or item.get("id"),
                    "bvid": item.get("bvid", ""),
                    "标题": title.strip(),
                    "up主": item.get("author", ""),
                    "简介": (item.get("description") or "").strip(),
                    "播放": item.get("play") or 0,
                    "弹幕": item.get("video_review") or 0,
                    "时长": item.get("duration", ""),
                    "发布": item.get("pubdate") or 0,
                    "分区": item.get("typename", ""),
                }
            )
        return results

    async def fetch_detail(
        self, session: aiohttp.ClientSession, bvid: str
    ) -> dict[str, Any] | None:
        payload = await self._get(session, VIEW_API, {"bvid": bvid})
        if payload.get("code") != 0:
            return None
        data = payload.get("data") or {}
        description = (data.get("desc") or "").strip()
        return {
            "aid": data.get("aid"),
            "bvid": data.get("bvid", bvid),
            "标题": (data.get("title") or "").strip(),
            "up主": ((data.get("owner") or {}).get("name")) or "",
            "简介": description[:300],
            "播放": ((data.get("stat") or {}).get("view")) or 0,
            "弹幕": ((data.get("stat") or {}).get("danmaku")) or 0,
            "发布": data.get("pubdate") or 0,
            "分区": ((data.get("tname")) or ""),
        }

    async def post_comment(
        self,
        session: aiohttp.ClientSession,
        aid: int,
        content: str,
    ) -> int:
        """在视频下发一条顶层评论，返回 rpid。"""
        async with session.post(
            REPLY_API,
            data={
                "oid": aid,
                "type": 1,
                "message": content,
                "csrf": self._bili_jct,
                "plat": 1,
            },
            headers=self._headers(),
            timeout=aiohttp.ClientTimeout(total=20),
        ) as response:
            payload = await response.json(content_type=None)
        if not isinstance(payload, dict):
            raise ApiError(f"发评论返回体不是对象：{response.status}")
        code = payload.get("code")
        if code != 0:
            reason = REPLY_ERROR_CODES.get(code) or payload.get("message") or "未知原因"
            raise ApiError(f"发评论失败 code={code}：{reason}")
        return int(((payload.get("data") or {}).get("rpid")) or 0)

    async def _post(
        self,
        session: aiohttp.ClientSession,
        url: str,
        data: dict[str, Any],
        label: str,
    ) -> dict[str, Any]:
        """带 csrf 的写操作。非 0 业务码一律翻成 `接口错误`。"""
        async with session.post(
            url,
            data={**data, "csrf": self._bili_jct},
            headers=self._headers(),
            timeout=aiohttp.ClientTimeout(total=15),
        ) as response:
            status = response.status
            text = await response.text()
        payload = parse_response(text, status, url)
        code = payload.get("code")
        if code != 0:
            raise ApiError(f"{label}失败 code={code}：{payload.get('message') or '未知原因'}")
        return payload

    async def _my_mid(self, session: aiohttp.ClientSession) -> int:
        if self._mid:
            return self._mid
        payload = await self._get(session, NAV_API, {})
        mid = (payload.get("data") or {}).get("mid")
        if not mid:
            raise ApiError("登录态失效，导航接口没返回 mid")
        self._mid = int(mid)
        return self._mid

    async def _default_fav(self, session: aiohttp.ClientSession) -> str:
        """取账号下第一个收藏夹。列表按创建时间排，第一个就是默认的。"""
        if self._fav_id:
            return self._fav_id
        payload = await self._get(session, FAV_LIST_API, {"up_mid": await self._my_mid(session)})
        items = (payload.get("data") or {}).get("list") or []
        if not items:
            raise ApiError("账号下没有收藏夹，建一个再试")
        self._fav_id = str(items[0]["id"])
        return self._fav_id

    async def like(self, session: aiohttp.ClientSession, aid: int) -> None:
        await self._post(session, LIKE_API, {"aid": aid, "like": 1}, "点赞")

    async def favorite(self, session: aiohttp.ClientSession, aid: int) -> None:
        await self._post(
            session,
            FAV_API,
            {"rid": aid, "type": 2, "add_media_ids": await self._default_fav(session)},
            "收藏",
        )
