"""atpy：每天随机几轮，从B站捞一个怪视频，@朋友，留一句十字以内的锐评。

跟爱瓦 / 爱农 / 爱完美不同，这个插件不响应用户指令为主——它的主循环是
后台定时任务，指令只是用来手动触发和查状态。
"""

from __future__ import annotations

import asyncio
import random
import re
import time
from datetime import date, datetime
from datetime import time as 时间
from pathlib import Path
from typing import Any

import aiohttp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, MessageEventResult
from astrbot.api.event.filter import command_group, custom_filter, llm_tool
from astrbot.api.star import Context, Star
from astrbot.core.star.filter.custom_filter import CustomFilter

from .atpy import critic, pick
from .atpy.bili import B站客户端, 接口错误
from .atpy.store import 记录簿
from .atpy.兜底 import 以组名开头, 取落空参数, 帮助文本, 是否落空, 落空提示

_插件名 = "astrbot_plugin_bilibili_atpy"
_组名 = "atpy"

# QQ 官方适配器在 `@机器人` 唤醒时 `wake_prefix = ""`，**不剥掉 message_str
# 里的 `/`**（只有 startswith 分支才剥）。于是 message_str 仍是 `/atpy 状态`，
# 组名 `atpy` 匹配不上，整条指令静默失败、消息进模型。加一个带斜杠的别名，
# 两种写法都能进。
_组别名 = {f"/{_组名}"}


def _文本(配置: AstrBotConfig, 键: str, 默认: str = "") -> str:
    值 = 配置.get(键)
    return str(值).strip() if isinstance(值, str) else 默认


def _整数(配置: AstrBotConfig, 键: str, 默认: int) -> int:
    值 = 配置.get(键)
    try:
        return int(值)
    except (TypeError, ValueError):
        return 默认


def _开关(配置: AstrBotConfig, 键: str, 默认: bool) -> bool:
    值 = 配置.get(键)
    return bool(值) if isinstance(值, bool) else 默认


def _拆分(原串: str) -> list[str]:
    """按中英文逗号和顿号切分，去掉空白项。昵称里的空格保持原样。"""
    return [段.strip() for 段 in re.split(r"[,，、]", 原串 or "") if 段.strip()]


class _落空兜底(CustomFilter):
    """`/atpy <不是子命令>` 时自己接住，别让消息流到模型手里。

    `filter` 的返回值语义是「这条消息我管不管」，**不是**「我有没有命中」——
    `CommandGroupFilter.filter` 里 `if not self.custom_filter_ok(...): return False`，
    返回 False 会把整个指令组毙掉。所以这里恒返回 True：命中就自己给结果并
    `stop_event()`，没命中就放行给子指令。写成「命中返回 False」会让
    `/atpy 状态` 这种正常指令完全没反应。
    """

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        文本 = getattr(event, "message_str", "") or ""
        # 这条过滤器对**每一条消息**都会跑（CommandGroupFilter 先跑
        # custom_filter_ok 再检查组名），所以第一件事是判断关不关我事。
        if not 以组名开头(文本, _组名):
            return True
        logger.debug(f"[{_组名}] 指令命中 message_str={文本!r}")
        if 是否落空(文本, _组名):
            event.set_result(MessageEventResult().message(落空提示(取落空参数(文本, _组名))))
            event.stop_event()
        return True


class Atpy(Star):
    # 别写成 `self.atpy.add_custom_filter(...)`——`self.atpy` 是
    # `RegisteringCommandable`，没有那个方法，加载时会 AttributeError。
    @custom_filter(_落空兜底)
    @command_group(_组名, alias=_组别名)
    def atpy(self):
        """在B站评论区给朋友整活。指令都在这个组下，不占用通用名字。"""

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config
        self._随机 = random.Random()
        self._记录簿 = 记录簿(self._数据目录())
        self._后台任务: asyncio.Task | None = None

        self._朋友 = _拆分(_文本(config, "friends"))
        self._客户端 = B站客户端(_文本(config, "sessdata"), _文本(config, "bili_jct"))
        self._通知会话 = _文本(config, "notify_umo")
        self._只预览 = _开关(config, "dry_run", False)
        self._门槛 = pick.门槛(
            最少播放=_整数(config, "min_play", 10000),
            最多播放=_整数(config, "max_play", 5000000),
            最多几天前=_整数(config, "max_days_old", 0),
        )

        # 会话标识是「平台:群类型:群号」三段。少一段 send_message 找不到会话，
        # 通知被静默丢掉，日志里只有一行 warning，很难发现。
        if self._通知会话 and self._通知会话.count(":") < 2:
            logger.warning(
                f"[{_组名}] notify_umo 不像完整会话标识：{self._通知会话}。"
                f"应该是 `平台:群类型:群号`，在群里发 /{_组名} UMO 取整串。"
            )

        if _开关(config, "enabled", True):
            self._后台任务 = asyncio.create_task(self._调度())
            logger.info(
                f"[{_组名}] 后台调度已启动：每天 {_整数(config, 'rounds_min', 1)}"
                f"-{_整数(config, 'rounds_max', 1)} 轮，"
                f"{_整数(config, 'active_start_hour', 9)}-"
                f"{_整数(config, 'active_end_hour', 23)} 点之间"
            )

    # ── 基础设施 ──

    def _数据目录(self) -> Path:
        from astrbot.core.star.star_tools import StarTools

        return StarTools.get_data_dir(_插件名)

    def _生成排期(self, 当天: date) -> list[int]:
        """把活跃时段切成 N 段，每段随机取一个点。

        纯随机取 N 个点容易挤成一堆，分段之后间隔天然散开，看起来像人。
        """
        起 = datetime.combine(当天, 时间(hour=_整数(self.config, "active_start_hour", 9)))
        止 = datetime.combine(当天, 时间(hour=_整数(self.config, "active_end_hour", 23)))
        if 止 <= 起:
            return []
        下 = _整数(self.config, "rounds_min", 1)
        上 = _整数(self.config, "rounds_max", 1)
        轮数 = self._随机.randint(min(下, 上), max(下, 上))
        跨度 = (止 - 起).total_seconds()
        现在 = time.time()
        时刻: list[int] = []
        for 序号 in range(轮数):
            段起 = 起.timestamp() + 跨度 * 序号 / 轮数
            段止 = 起.timestamp() + 跨度 * (序号 + 1) / 轮数
            # 今天已经过去的时间段不排，避免一启动就补发一串。
            if 段止 <= 现在:
                continue
            点 = max(段起, 现在) + self._随机.random() * max(0.0, 段止 - max(段起, 现在))
            时刻.append(int(点))
        return sorted(时刻)

    async def _调度(self) -> None:
        try:
            while True:
                try:
                    await self._到点就跑()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(f"[{_组名}] 本轮执行出错")
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise

    async def _到点就跑(self) -> None:
        当天 = date.today()
        键 = 当天.isoformat()
        排期 = self._记录簿.取排期(键)
        if 排期 is None:
            排期 = self._生成排期(当天)
            self._记录簿.存排期(键, 排期)
            if 排期:
                logger.info(
                    f"[{_组名}] 今天排了 {len(排期)} 轮："
                    + "、".join(datetime.fromtimestamp(点).strftime("%H:%M") for 点 in 排期)
                )
            else:
                logger.warning(f"[{_组名}] 今天没有可用的排期，检查活跃时段配置")
            return
        if not 排期:
            return

        现在 = time.time()
        # 超过十分钟的档期不补跑，否则容器重启会把攒下的几轮一起放出来。
        剩余 = [点 for 点 in 排期 if 点 > 现在 - 600]
        if 剩余 != 排期:
            self._记录簿.存排期(键, 剩余)
            排期 = 剩余
        到点 = [点 for 点 in 排期 if 点 <= 现在]
        if not 到点:
            return

        本轮 = 到点[0]
        self._记录簿.存排期(键, [点 for 点 in 排期 if 点 != 本轮])
        logger.info(f"[{_组名}] 到点开跑（预约 {datetime.fromtimestamp(本轮):%H:%M}）")
        await self._跑一轮()

    # ── 主流程 ──

    async def _跑一轮(self, 只预览: bool = False) -> dict[str, Any]:
        """找片、写评、发出去。返回结果字典，指令和日志共用。"""
        真的要发 = not (只预览 or self._只预览)
        if 真的要发 and not self._客户端.有登录态():
            return {"成功": False, "原因": "没配 sessdata 或 bili_jct，发不了评论"}
        if 真的要发 and not self._朋友:
            return {"成功": False, "原因": "没配朋友昵称，不知道 @ 谁"}

        已发过 = self._记录簿.已发过的()
        自定义 = _拆分(_文本(self.config, "keywords"))
        类别 = pick.按天取类别(date.today())

        async with aiohttp.ClientSession() as 会话:
            视频 = await self._找片(会话, 已发过, 自定义, 类别)
            if 视频 is None:
                return {"成功": False, "原因": f"「{类别}」这条线三个词都没找到合适的片子"}

            await self._补简介(会话, 视频)
            锐评 = await self._写评(视频)
            if not critic.可用(锐评):
                return {"成功": False, "原因": "模型没给出能用的锐评", "视频": 视频}

            文本 = f"{' '.join('@' + 名 for 名 in self._朋友)} {锐评}".strip()
            结果: dict[str, Any] = {
                "视频": 视频,
                "锐评": 锐评,
                "评论": 文本,
                "类别": 类别,
            }

            if not 真的要发:
                结果["成功"] = True
                结果["原因"] = "预览模式，没有真的发出去"
                logger.info(f"[{_组名}] 预览：{视频.get('标题')} → {文本}")
                return 结果

            try:
                rpid = await self._客户端.发评论(会话, int(视频["aid"]), 文本)
            except (接口错误, aiohttp.ClientError) as 错:
                logger.warning(f"[{_组名}] {错}")
                return {"成功": False, "原因": str(错), **结果}

        self._记录簿.追加(
            {
                "bvid": 视频.get("bvid", ""),
                "aid": 视频.get("aid"),
                "标题": 视频.get("标题", ""),
                "up主": 视频.get("up主", ""),
                "播放": 视频.get("播放", 0),
                "锐评": 锐评,
                "评论": 文本,
                "rpid": rpid,
            }
        )
        结果["成功"] = True
        结果["rpid"] = rpid
        logger.info(f"[{_组名}] 已发：{视频.get('标题')} → {文本}")
        await self._通知(视频, 文本)
        return 结果

    async def _找片(
        self,
        会话: aiohttp.ClientSession,
        已发过: set[str],
        自定义: list[str],
        类别: str,
    ) -> dict[str, Any] | None:
        """在今天的类别里最多换三个关键词。每个词只搜一次，不去翻页。"""
        for 第几次 in range(3):
            if 第几次:
                # 连着打搜索接口容易吃 412，隔一两秒再问。
                await asyncio.sleep(self._随机.uniform(1.0, 2.5))
            词 = pick.抽关键词(self._随机, 自定义, 类别)
            try:
                候选 = await self._客户端.搜索视频(会话, 词, 条数=50, 排序="totalrank")
            except (接口错误, aiohttp.ClientError) as 错:
                logger.warning(f"[{_组名}] 搜「{词}」失败：{错}")
                continue
            选中的 = pick.挑一个(self._随机, 候选, 已发过, self._门槛)
            if 选中的:
                logger.info(f"[{_组名}] 「{类别}」选中「{词}」：{选中的.get('标题')}")
                return 选中的
            logger.info(f"[{_组名}] 「{词}」搜到 {len(候选)} 条，都不合格")
        return None

    async def _补简介(self, 会话: aiohttp.ClientSession, 视频: dict[str, Any]) -> None:
        """搜索结果里的简介常被截断，模型的判断需要完整一点。失败就保持原样。"""
        if len(视频.get("简介") or "") >= 60:
            return
        try:
            详情 = await self._客户端.取详情(会话, 视频.get("bvid", ""))
        except (接口错误, aiohttp.ClientError):
            return
        if 详情:
            视频.update({键: 值 for 键, 值 in 详情.items() if 值})

    async def _写评(self, 视频: dict[str, Any]) -> str:
        提示 = critic.拼提示词(视频)
        原文 = await self._调模型(提示)
        return critic.清洗(原文)

    async def _调模型(self, 提示: str) -> str:
        实例 = await self._取模型()
        if 实例 is None:
            return ""
        try:
            回复 = await asyncio.wait_for(
                实例.text_chat(
                    prompt=提示,
                    system_prompt=critic.系统提示,
                    request_max_retries=1,
                ),
                timeout=_整数(self.config, "model_timeout_seconds", 60),
            )
        except asyncio.TimeoutError:
            logger.warning(f"[{_组名}] 模型超时")
            return ""
        except Exception as 错:
            # 上游 429、鉴权失效、网络中断都会从这里出。这一轮废掉即可，
            # 别让它冒到调度循环里显得像插件崩了。
            logger.warning(f"[{_组名}] 模型调用失败：{type(错).__name__} {错}")
            return ""
        return (getattr(回复, "completion_text", "") or "").strip()

    async def _取模型(self):
        指定 = _文本(self.config, "provider_id")
        管理器 = self.context.provider_manager
        if 指定:
            实例 = await 管理器.get_provider_by_id(指定)
            if 实例 is None:
                logger.warning(f"[{_组名}] 配置的模型 {指定!r} 不存在")
            return 实例
        实例们 = 管理器.get_insts()
        if not 实例们:
            logger.warning(f"[{_组名}] 没有可用的对话模型")
            return None
        return 实例们[0]

    async def _通知(self, 视频: dict[str, Any], 文本: str) -> None:
        """在配置的会话里说一句，让群里知道它刚才干了什么。"""
        if not self._通知会话:
            return
        链接 = f"https://www.bilibili.com/video/{视频.get('bvid', '')}"
        消息 = f"刚刷到一个：{视频.get('标题', '')}\n{文本}\n{链接}"
        try:
            await self.context.send_message(self._通知会话, MessageChain().message(消息))
        except Exception as 错:
            logger.warning(f"[{_组名}] 通知发送失败：{错}")

    # ── 指令 ──

    @atpy.command("现在", alias={"跑"})
    async def 现在(self, event: AstrMessageEvent):
        """立刻跑一轮。会真的发评论。"""
        event.stop_event()
        yield event.plain_result(self._结果文本(await self._跑一轮()))

    @atpy.command("预览")
    async def 预览(self, event: AstrMessageEvent):
        """只选片和写评，不发评论。"""
        event.stop_event()
        yield event.plain_result(self._结果文本(await self._跑一轮(只预览=True)))

    @atpy.command("最近")
    async def 最近(self, event: AstrMessageEvent):
        """最近发过的五条。"""
        event.stop_event()
        记录 = self._记录簿.最近(5)
        if not 记录:
            yield event.plain_result("还没发过。")
            return
        行 = [
            f"{datetime.fromtimestamp(条['时间']):%m-%d %H:%M} {条.get('标题', '')}\n"
            f"　{条.get('评论', '')}"
            for 条 in 记录
        ]
        yield event.plain_result("\n".join(行))

    @atpy.command("状态")
    async def 状态(self, event: AstrMessageEvent):
        """登录态、今日剩余档期。"""
        event.stop_event()
        yield event.plain_result(self._状态文本())

    @atpy.command("UMO", alias={"umo"})
    async def 取UMO(self, event: AstrMessageEvent):
        """取当前会话标识，填进「通知会话」配置。"""
        event.stop_event()
        yield event.plain_result(
            f"{event.unified_msg_origin}\n"
            f"整行复制（含开头的平台名和两段冒号），填进插件配置的「通知会话」。"
        )

    @atpy.command("帮助", alias={"help", "菜单"})
    async def 帮助(self, event: AstrMessageEvent):
        """列出全部指令。"""
        event.stop_event()
        yield event.plain_result(帮助文本(_组名))

    @llm_tool(name="recent_bili_critics")
    async def 查最近锐评(self, event: AstrMessageEvent) -> str:
        """查这个机器人最近在B站发过的锐评，用于聊天时提起自己刷到过什么。

        Returns:
            最近五条记录的标题、锐评和视频链接。还没发过时返回说明文字。
        """
        记录 = self._记录簿.最近(5)
        if not 记录:
            return "还没在B站发过锐评。"
        行 = []
        for 条 in 记录:
            时间 = datetime.fromtimestamp(条["时间"]).strftime("%m-%d %H:%M")
            行.append(
                f"{时间}｜{条.get('标题', '')}｜锐评：{条.get('锐评', '')}"
                f"｜https://www.bilibili.com/video/{条.get('bvid', '')}"
            )
        return "\n".join(行)

    def _结果文本(self, 结果: dict[str, Any]) -> str:
        if 结果.get("成功"):
            行 = [
                f"发了：{结果['视频'].get('标题', '')}",
                f"评论：{结果.get('评论', '')}",
                f"https://www.bilibili.com/video/{结果['视频'].get('bvid', '')}",
            ]
            if 结果.get("原因"):
                行.append(结果["原因"])
            return "\n".join(行)
        return f"这一轮没成：{结果.get('原因', '原因不明')}"

    def _状态文本(self) -> str:
        键 = date.today().isoformat()
        排期 = self._记录簿.取排期(键)
        剩余 = "、".join(datetime.fromtimestamp(点).strftime("%H:%M") for 点 in 排期)
        登录 = "已配" if self._客户端.有登录态() else "没配"
        朋友 = "、".join(self._朋友) if self._朋友 else "没配"
        后台 = "运行中" if self._后台任务 and not self._后台任务.done() else "未启动"
        return (
            f"后台：{后台}\n"
            f"B站登录：{登录}\n"
            f"@ 的对象：{朋友}\n"
            f"今日剩余：{剩余 or '没了'}\n"
            f"预览模式：{'开' if self._只预览 else '关'}"
        )

    async def terminate(self) -> None:
        if self._后台任务 and not self._后台任务.done():
            self._后台任务.cancel()
            try:
                await self._后台任务
            except asyncio.CancelledError:
                pass
