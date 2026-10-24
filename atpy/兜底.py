"""指令落空时的兜底。

`/atpy <不是子命令>` 时 `CommandGroupFilter.filter` 返回 False，指令被跳过，
**消息原样进模型**——模型会自己编答案或联网搜。线上实测：把 `/atpy UMO` 打错
成 `/aipy UMO`，机器人去搜了「aipy 是什么」。

所以指令组挂一个兜底过滤器，匹配了组名但没匹配子命令时自己回提示。
只拦「以组名开头」的；`/atpy` 单独一条由 AstrBot 自己列出子命令，不重复。
"""

from __future__ import annotations

__all__ = ["子命令名", "以组名开头", "取落空参数", "是否落空", "落空提示", "帮助文本"]

# 全部子命令与别名。少一个别名，用户打那个别名时就落空了。
# 改 main.py 里的指令或别名，这里要跟着改——`test_main_wiring.py` 会核对。
子命令名 = frozenset(
    {
        "现在",
        "预览",
        "最近",
        "状态",
        "帮助",
        "UMO",
        "umo",
        "跑",
        "help",
        "菜单",
    }
)


def 以组名开头(消息: str, 组名: str) -> bool:
    """这条消息是不是以指令组名开头。

    **必须有这一层判断**：`CommandGroupFilter.filter` 先跑 `custom_filter_ok()`
    再检查组名，所以挂在这里的过滤器对**每一条消息**都会执行，包括别的插件的
    指令。没有这道闸，「爱农 状态」会被判成 atpy 落空，`stop_event()` 掐死别人的指令。
    """
    文本 = (消息 or "").strip()
    return 文本.startswith(f"/{组名}") or 文本.startswith(组名)


def 取落空参数(消息: str, 组名: str) -> str:
    """取出组名后面的内容。

    QQ 官方适配器有时剥掉 `message_str` 里的 `/`，两种写法都得认。
    不以组名开头时返回空串，**不是原样返回**——调用方靠这一点判断「不归我管」。
    """
    文本 = (消息 or "").strip()
    for 前缀 in (f"/{组名}", 组名):
        if 文本.startswith(前缀):
            return 文本[len(前缀) :].strip()
    return ""


def 是否落空(消息: str, 组名: str) -> bool:
    """这条消息是不是「匹配了组名但没匹配任何子命令」。

    判据必须与 `CommandGroupFilter.startswith` 一致——**字面前缀匹配**，否则
    会吃掉正常指令。消息完全等于组名（`/atpy`）不算落空，那时 AstrBot 自己
    会列出全部子指令，两组提示会叠着发。
    """
    if not 以组名开头(消息, 组名):
        # 不是发给我的，放行。别碰别人的指令。
        return False
    参数 = 取落空参数(消息, 组名)
    if not 参数:
        return False
    return not any(参数.startswith(名) for 名 in 子命令名)


def 落空提示(参数: str, 组名: str) -> str:
    """没有子命令匹配时回什么。"""
    干净 = (参数 or "").strip()
    if not 干净:
        return f"没认出要做什么。发 ／{组名} 帮助 看全部。"

    # 参数短就原样带回去让用户看清自己发了什么，太长就截断——
    # 一整段东西回显出来没意义。
    回显 = 干净 if len(干净) <= 30 else f"{干净[:30]}…"
    return f"「{回显}」不是子命令。发 ／{组名} 帮助 看全部。"


def 帮助文本(组名: str) -> str:
    """`/atpy 帮助` 的回复。"""
    return (
        f"／{组名} 现在    跑一轮，会真的发评论\n"
        f"／{组名} 预览    只选片写评，不发\n"
        f"／{组名} 最近    最近发过的几条\n"
        f"／{组名} 状态    登录态、今日排期\n"
        f"／{组名} UMO     取会话标识\n"
        f"／{组名} 帮助    这张表"
    )
