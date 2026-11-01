from atpy.fallback import is_command_miss, leftover_arg, miss_hint, starts_with_group

group = "atpy"


def test_accepts_with_and_without_slash():
    assert starts_with_group("/atpy 状态", group)
    assert starts_with_group("atpy 状态", group)
    assert not starts_with_group("/爱农 战绩", group)
    assert not starts_with_group("", group)


def test_ignores_other_plugins_commands():
    """`取落空参数` 对不属于本组的消息返回空串，不是原样返回。

    返回原样会让别的插件的指令被判成自己的落空，stop_event 把人家掐死。
    """
    assert leftover_arg("/爱农 战绩", group) == ""
    assert leftover_arg("/atpy 状态", group) == "状态"
    assert leftover_arg("atpy UMO", group) == "UMO"


def test_valid_subcommand_is_not_miss():
    for message in ("/atpy 现在", "/atpy 预览", "/atpy 最近", "/atpy 状态", "/atpy 帮助"):
        assert not is_command_miss(message, group), message
    assert not is_command_miss("/atpy UMO", group)
    assert not is_command_miss("/atpy umo", group)


def test_unknown_content_is_miss():
    assert is_command_miss("/atpy 瞎写", group)
    assert is_command_miss("/atpy aipy UMO", group)


def test_similar_prefix_is_not_miss():
    """`/aipy` 只差一个字母，但那是别人的指令，不该被本组接管。"""
    assert not is_command_miss("/aipy UMO", group)


def test_bare_group_name_is_not_miss():
    """`/atpy` 单独一条由 AstrBot 自己列出子命令，不归兜底管。"""
    assert not is_command_miss("/atpy", group)
    assert not is_command_miss("/atpy   ", group)


def test_miss_hint_echoes_argument():
    hint = miss_hint("瞎写", group)
    assert "瞎写" in hint
    assert f"／{group} 帮助" in hint


def test_miss_hint_truncates_long_argument():
    short_hint = miss_hint("瞎写", group)
    long_hint = miss_hint("一" * 100, group)
    assert "…" in long_hint
    assert len(long_hint) - len(short_hint) <= 40
