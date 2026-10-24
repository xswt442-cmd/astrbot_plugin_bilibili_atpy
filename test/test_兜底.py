from atpy.兜底 import 以组名开头, 取落空参数, 是否落空, 落空提示

组 = "atpy"


def test_认带斜杠和不带的两种写法():
    assert 以组名开头("/atpy 状态", 组)
    assert 以组名开头("atpy 状态", 组)
    assert not 以组名开头("/爱农 战绩", 组)
    assert not 以组名开头("", 组)


def test_别人的指令不许碰():
    """`取落空参数` 对不属于本组的消息返回空串，不是原样返回。

    返回原样会让别的插件的指令被判成自己的落空，stop_event 把人家掐死。
    """
    assert 取落空参数("/爱农 战绩", 组) == ""
    assert 取落空参数("/atpy 状态", 组) == "状态"
    assert 取落空参数("atpy UMO", 组) == "UMO"


def test_正常子命令不算落空():
    for 消息 in ("/atpy 现在", "/atpy 预览", "/atpy 最近", "/atpy 状态", "/atpy 帮助"):
        assert not 是否落空(消息, 组), 消息
    assert not 是否落空("/atpy UMO", 组)
    assert not 是否落空("/atpy umo", 组)


def test_不认识的内容算落空():
    assert 是否落空("/atpy 瞎写", 组)
    assert 是否落空("/atpy aipy UMO", 组)


def test_别组的前缀不算落空():
    """`/aipy` 只差一个字母，但那是别人的指令，不该被本组接管。"""
    assert not 是否落空("/aipy UMO", 组)


def test_只有组名不算落空():
    """`/atpy` 单独一条由 AstrBot 自己列出子命令，不归兜底管。"""
    assert not 是否落空("/atpy", 组)
    assert not 是否落空("/atpy   ", 组)


def test_落空提示带回显():
    提示 = 落空提示("瞎写", 组)
    assert "瞎写" in 提示
    assert f"／{组} 帮助" in 提示


def test_落空提示截断长内容():
    短 = 落空提示("瞎写", 组)
    长 = 落空提示("一" * 100, 组)
    assert "…" in 长
    assert len(长) - len(短) <= 40
