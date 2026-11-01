"""atpy：每天从B站捞一个视频，@朋友，留一句十字以内的锐评。

跟爱瓦 / 爱农 / 爱完美不同，主循环是后台定时任务，指令只用来手动触发和查状态。
"""

from __future__ import annotations

import asyncio
import random
import re
import time
from datetime import date, datetime
from datetime import time as dt_time
from pathlib import Path
from typing import Any

import aiohttp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, MessageEventResult
from astrbot.api.event.filter import command_group, custom_filter, llm_tool
from astrbot.api.star import Context, Star
from astrbot.core.star.filter.custom_filter import CustomFilter

from .atpy import critic, pick
from .atpy.bili import ApiError, BiliClient
from .atpy.fallback import help_text, is_command_miss, leftover_arg, miss_hint, starts_with_group
from .atpy.store import RecordBook

_PLUGIN_NAME = "astrbot_plugin_bilibili_atpy"
_GROUP = "atpy"

# QQ 官方适配器在 `@机器人` 唤醒时 `wake_prefix = ""`，**不剥掉 message_str 里的
# `/`**。message_str 仍是 `/atpy 状态`，只有组名 `atpy` 匹配不上，整条指令静默
# 失败、消息进模型。加一个带斜杠的别名，两种写法都能进。
_GROUP_ALIASES = {f"/{_GROUP}"}


def _text(config: AstrBotConfig, key: str, default: str = "") -> str:
    value = config.get(key)
    return str(value).strip() if isinstance(value, str) else default


def _int(config: AstrBotConfig, key: str, default: int) -> int:
    value = config.get(key)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _flag(config: AstrBotConfig, key: str, default: bool) -> bool:
    value = config.get(key)
    return bool(value) if isinstance(value, bool) else default


def _split(raw: str) -> list[str]:
    """按中英文逗号和顿号切分，去掉空白项。昵称里的空格保持原样。"""
    return [segment.strip() for segment in re.split(r"[,，、]", raw or "") if segment.strip()]


class _MissFallbackFilter(CustomFilter):
    """`/atpy <不是子命令>` 时自己接住，别让消息流到模型手里。

    `filter` 的返回值语义是「这条消息我管不管」，**不是**「我有没有命中」——
    `CommandGroupFilter.filter` 里 `if not self.custom_filter_ok(...): return False`。
    所以这里恒返回 True：命中就自己给结果并 `stop_event()`，没命中就放行。
    """

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        text = getattr(event, "message_str", "") or ""
        # 这条过滤器对**每一条消息**都会跑（CommandGroupFilter 先跑
        # custom_filter_ok 再检查组名），所以第一件事是判断关不关我事。
        if not starts_with_group(text, _GROUP):
            return True
        if is_command_miss(text, _GROUP):
            event.set_result(
                MessageEventResult().message(miss_hint(leftover_arg(text, _GROUP), _GROUP))
            )
            event.stop_event()
        return True


class Atpy(Star):
    # 别写成 `self.atpy.add_custom_filter(...)`——`self.atpy` 是
    # `RegisteringCommandable`，没有那个方法，加载时会 AttributeError。
    @custom_filter(_MissFallbackFilter)
    @command_group(_GROUP, alias=_GROUP_ALIASES)
    def atpy(self):
        """在B站评论区给朋友整活。指令都在这个组下，不占用通用名字。"""

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config
        self._rng = random.Random()
        self._records = RecordBook(self._data_dir())
        self._task: asyncio.Task | None = None

        self._friends = _split(_text(config, "friends"))
        self._client = BiliClient(_text(config, "sessdata"), _text(config, "bili_jct"))
        self._notify_umo = _text(config, "notify_umo")
        self._dry_run = _flag(config, "dry_run", False)
        self._threshold = pick.Threshold(
            min_play=_int(config, "min_play", 10000),
            max_play=_int(config, "max_play", 5000000),
            max_days_old=_int(config, "max_days_old", 0),
        )

        # 会话标识是「平台:群类型:群号」三段。少一段 send_message 找不到会话，
        # 通知被静默丢掉，日志里只有一行 warning，很难发现。
        if self._notify_umo and self._notify_umo.count(":") < 2:
            logger.warning(
                f"[{_GROUP}] notify_umo 不像完整会话标识：{self._notify_umo}。"
                f"应为 `平台:群类型:群号`，在群里发 ／{_GROUP} UMO 取整串。"
            )

        if _flag(config, "enabled", True):
            self._task = asyncio.create_task(self._scheduler())
            logger.info(
                f"[{_GROUP}] 后台调度已启动：每天 {_int(config, 'rounds_min', 1)}"
                f"-{_int(config, 'rounds_max', 1)} 轮，"
                f"{_int(config, 'active_start_hour', 9)}-"
                f"{_int(config, 'active_end_hour', 23)} 点之间"
            )

    # ── 基础设施 ──

    def _data_dir(self) -> Path:
        from astrbot.core.star.star_tools import StarTools

        return StarTools.get_data_dir(_PLUGIN_NAME)

    def _build_schedule(self, day: date) -> list[int]:
        """把活跃时段切成 N 段，每段随机取一个点。

        纯随机取 N 个点容易挤成一堆，分段之后间隔天然散开。
        """
        start = datetime.combine(day, dt_time(hour=_int(self.config, "active_start_hour", 9)))
        end = datetime.combine(day, dt_time(hour=_int(self.config, "active_end_hour", 23)))
        if end <= start:
            return []
        low = _int(self.config, "rounds_min", 1)
        high = _int(self.config, "rounds_max", 1)
        rounds = self._rng.randint(min(low, high), max(low, high))
        span = (end - start).total_seconds()
        now = time.time()
        slots: list[int] = []
        for index in range(rounds):
            seg_start = start.timestamp() + span * index / rounds
            seg_end = start.timestamp() + span * (index + 1) / rounds
            # 今天已经过去的时间段不排，避免一启动就补发一串。
            if seg_end <= now:
                continue
            point = max(seg_start, now) + self._rng.random() * max(
                0.0, seg_end - max(seg_start, now)
            )
            slots.append(int(point))
        return sorted(slots)

    async def _scheduler(self) -> None:
        try:
            while True:
                try:
                    await self._run_due()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(f"[{_GROUP}] 本轮执行出错")
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise

    async def _run_due(self) -> None:
        day = date.today()
        key = day.isoformat()
        schedule = self._records.get_schedule(key)
        if schedule is None:
            schedule = self._build_schedule(day)
            self._records.set_schedule(key, schedule)
            if schedule:
                logger.info(
                    f"[{_GROUP}] 今天排了 {len(schedule)} 轮："
                    + "、".join(
                        datetime.fromtimestamp(point).strftime("%H:%M") for point in schedule
                    )
                )
            else:
                logger.warning(f"[{_GROUP}] 今天没有可用的排期，检查活跃时段配置")
            return
        if not schedule:
            return

        now = time.time()
        # 超过十分钟的档期不补跑，否则容器重启会把攒下的几轮一起放出来。
        remaining = [point for point in schedule if point > now - 600]
        if remaining != schedule:
            self._records.set_schedule(key, remaining)
            schedule = remaining
        due = [point for point in schedule if point <= now]
        if not due:
            return

        current = due[0]
        self._records.set_schedule(key, [point for point in schedule if point != current])
        logger.info(f"[{_GROUP}] 到点开跑（预约 {datetime.fromtimestamp(current):%H:%M}）")
        await self._run_round()

    # ── 主流程 ──

    async def _run_round(self, dry_run: bool = False) -> dict[str, Any]:
        """找片、写评、发出去。返回结果字典，指令和日志共用。"""
        should_post = not (dry_run or self._dry_run)
        if should_post and not self._client.has_login():
            return {"成功": False, "原因": "没配 B站登录态，发不了评论"}
        if should_post and not self._friends:
            return {"成功": False, "原因": "没配朋友昵称，不知道 @ 谁"}

        sent = self._records.sent_bvids()
        custom = _split(_text(self.config, "keywords"))
        category = pick.category_for_date(date.today())

        async with aiohttp.ClientSession() as session:
            video = await self._find_video(session, sent, custom, category)
            if video is None:
                return {"成功": False, "原因": f"「{category}」三个词都没找到合适的片子"}

            await self._fill_description(session, video)
            critique = await self._write_critique(video)
            if not critic.is_usable(critique):
                return {"成功": False, "原因": "模型没给出能用的锐评", "视频": video}

            text = f"{' '.join('@' + name for name in self._friends)} {critique}".strip()
            result: dict[str, Any] = {
                "视频": video,
                "锐评": critique,
                "评论": text,
                "类别": category,
            }

            if not should_post:
                result["成功"] = True
                result["原因"] = "预览，没真发"
                logger.info(f"[{_GROUP}] 预览：{video.get('标题')} → {text}")
                return result

            try:
                rpid = await self._client.post_comment(session, int(video["aid"]), text)
            except (ApiError, aiohttp.ClientError) as err:
                logger.warning(f"[{_GROUP}] {err}")
                return {"成功": False, "原因": str(err), **result}

            # 顺手赞一下收一下。这两步失败不影响评论已经发出去的事实，
            # 所以只记日志，不改这一轮的成败。
            for action, fn in (("点赞", self._client.like), ("收藏", self._client.favorite)):
                try:
                    await fn(session, int(video["aid"]))
                except (ApiError, aiohttp.ClientError) as err:
                    logger.warning(f"[{_GROUP}] {action}没成：{err}")
                await asyncio.sleep(0.5)

        self._records.append(
            {
                "bvid": video.get("bvid", ""),
                "aid": video.get("aid"),
                "标题": video.get("标题", ""),
                "up主": video.get("up主", ""),
                "播放": video.get("播放", 0),
                "锐评": critique,
                "评论": text,
                "rpid": rpid,
            }
        )
        result["成功"] = True
        result["rpid"] = rpid
        logger.info(f"[{_GROUP}] 已发：{video.get('标题')} → {text}")
        await self._notify(video, critique)
        return result

    async def _find_video(
        self,
        session: aiohttp.ClientSession,
        sent: set[str],
        custom: list[str],
        category: str,
    ) -> dict[str, Any] | None:
        """在今天的类别里最多换三个关键词。每个词只搜一次，不去翻页。"""
        for attempt in range(3):
            if attempt:
                # 连着打搜索接口容易吃 412，隔一两秒再问。
                await asyncio.sleep(self._rng.uniform(1.0, 2.5))
            word = pick.pick_keyword(self._rng, custom, category)
            try:
                candidates = await self._client.search_videos(
                    session, word, count=50, order="totalrank"
                )
            except (ApiError, aiohttp.ClientError) as err:
                logger.warning(f"[{_GROUP}] 搜「{word}」失败：{err}")
                continue
            chosen = pick.pick_one(self._rng, candidates, sent, self._threshold)
            if chosen:
                logger.info(f"[{_GROUP}] 「{category}」选中「{word}」：{chosen.get('标题')}")
                return chosen
            logger.info(f"[{_GROUP}] 「{word}」搜到 {len(candidates)} 条，都不合格")
        return None

    async def _fill_description(
        self, session: aiohttp.ClientSession, video: dict[str, Any]
    ) -> None:
        """搜索结果里的简介常被截断，模型的判断需要完整一点。失败就保持原样。"""
        if len(video.get("简介") or "") >= 60:
            return
        try:
            detail = await self._client.fetch_detail(session, video.get("bvid", ""))
        except (ApiError, aiohttp.ClientError):
            return
        if detail:
            video.update({key: value for key, value in detail.items() if value})

    async def _write_critique(self, video: dict[str, Any]) -> str:
        prompt = critic.build_prompt(video)
        raw = await self._call_model(prompt)
        return critic.clean(raw)

    async def _call_model(self, prompt: str) -> str:
        provider = await self._get_provider()
        if provider is None:
            return ""
        try:
            reply = await asyncio.wait_for(
                provider.text_chat(
                    prompt=prompt,
                    system_prompt=critic.SYSTEM_PROMPT,
                    request_max_retries=1,
                ),
                timeout=_int(self.config, "model_timeout_seconds", 60),
            )
        except asyncio.TimeoutError:
            logger.warning(f"[{_GROUP}] 模型超时")
            return ""
        except Exception as err:
            # 上游 429、鉴权失效、网络中断都从这里出。这一轮废掉即可，
            # 别让它冒到调度循环里显得像插件崩了。
            logger.warning(f"[{_GROUP}] 模型调用失败：{type(err).__name__} {err}")
            return ""
        return (getattr(reply, "completion_text", "") or "").strip()

    async def _get_provider(self):
        provider_id = _text(self.config, "provider_id")
        manager = self.context.provider_manager
        if provider_id:
            provider = await manager.get_provider_by_id(provider_id)
            if provider is None:
                logger.warning(f"[{_GROUP}] 配置的模型 {provider_id!r} 不存在")
            return provider
        providers = manager.get_insts()
        if not providers:
            logger.warning(f"[{_GROUP}] 没有可用的对话模型")
            return None
        return providers[0]

    async def _notify(self, video: dict[str, Any], critique: str) -> None:
        """在配置的会话里说一句，让群里知道它刚才干了什么。

        只说艾特了几个人，不列名单——QQ 会把 `@名字` 当 at 语法重渲染，
        名单里的英文名会被包成 `@//xxx/`，看着像发错了。
        """
        if not self._notify_umo:
            return
        link = f"https://www.bilibili.com/video/{video.get('bvid', '')}"
        message = (
            f"刚刷到一个：{video.get('标题', '')}\n"
            f"艾特了 {len(self._friends)} 个人｜{critique}\n{link}"
        )
        try:
            await self.context.send_message(self._notify_umo, MessageChain().message(message))
        except Exception as err:
            logger.warning(f"[{_GROUP}] 通知发送失败：{err}")

    # ── 指令 ──

    @atpy.command("现在", alias={"跑"})
    async def now_cmd(self, event: AstrMessageEvent):
        """立刻跑一轮。会真的发评论。"""
        event.stop_event()
        yield event.plain_result(self._result_text(await self._run_round()))

    @atpy.command("预览")
    async def preview_cmd(self, event: AstrMessageEvent):
        """只选片和写评，不发评论。"""
        event.stop_event()
        yield event.plain_result(self._result_text(await self._run_round(dry_run=True)))

    @atpy.command("最近")
    async def recent_cmd(self, event: AstrMessageEvent):
        """最近发过的五条。"""
        event.stop_event()
        records = self._records.recent(5)
        if not records:
            yield event.plain_result("还没发过。")
            return
        lines = [
            f"{datetime.fromtimestamp(entry['时间']):%m-%d %H:%M} {entry.get('标题', '')}\n"
            f"　{entry.get('评论', '')}"
            for entry in records
        ]
        yield event.plain_result("\n".join(lines))

    @atpy.command("状态")
    async def status_cmd(self, event: AstrMessageEvent):
        """登录态、今日剩余档期。"""
        event.stop_event()
        yield event.plain_result(self._status_text())

    @atpy.command("UMO", alias={"umo"})
    async def umo_cmd(self, event: AstrMessageEvent):
        """取当前会话标识，填进「通知会话」配置。"""
        event.stop_event()
        yield event.plain_result(
            f"{event.unified_msg_origin}\n整行复制（含开头的平台名）填进「通知会话」。"
        )

    @atpy.command("帮助", alias={"help", "菜单"})
    async def help_cmd(self, event: AstrMessageEvent):
        """列出全部指令。"""
        event.stop_event()
        yield event.plain_result(help_text(_GROUP))

    @llm_tool(name="recent_bili_critics")
    async def recent_critics_tool(self, event: AstrMessageEvent) -> str:
        """查这个机器人最近在B站发过的锐评，用于聊天时提起自己刷到过什么。

        Returns:
            最近五条记录的标题、锐评和视频链接。还没发过时返回说明文字。
        """
        records = self._records.recent(5)
        if not records:
            return "还没在B站发过锐评。"
        lines = []
        for entry in records:
            stamp = datetime.fromtimestamp(entry["时间"]).strftime("%m-%d %H:%M")
            lines.append(
                f"{stamp}｜{entry.get('标题', '')}｜锐评：{entry.get('锐评', '')}"
                f"｜https://www.bilibili.com/video/{entry.get('bvid', '')}"
            )
        return "\n".join(lines)

    def _result_text(self, result: dict[str, Any]) -> str:
        if not result.get("成功"):
            return f"这一轮没成：{result.get('原因', '原因不明')}"
        video = result["视频"]
        lines = [
            f"发了：{video.get('标题', '')}",
            f"艾特了 {len(self._friends)} 个人｜{result.get('锐评', '')}",
            f"https://www.bilibili.com/video/{video.get('bvid', '')}",
        ]
        if result.get("原因"):
            lines.append(result["原因"])
        return "\n".join(lines)

    def _status_text(self) -> str:
        # `取排期` 今天还没排过时返回 None，不能拿来迭代。
        schedule = self._records.get_schedule(date.today().isoformat()) or []
        remaining = "、".join(datetime.fromtimestamp(point).strftime("%H:%M") for point in schedule)
        login_state = "已配" if self._client.has_login() else "没配"
        friend_names = "、".join(self._friends) if self._friends else "没配"
        background = "运行中" if self._task and not self._task.done() else "未启动"
        return (
            f"后台：{background}\n"
            f"B站登录：{login_state}\n"
            f"@ 的对象：{friend_names}\n"
            f"今日类别：{pick.category_for_date(date.today())}\n"
            f"今日剩余：{remaining or '没了'}\n"
            f"预览：{'开' if self._dry_run else '关'}"
        )

    async def terminate(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
