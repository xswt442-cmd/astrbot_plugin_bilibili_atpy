"""响应体解析的收口逻辑。

线上崩过一次：风控返回 412 的 HTML，`响应.json()` 抛 `JSONDecodeError`，
而 `_补简介` 只捕 `接口错误`，异常一路冒到调度循环，整轮评论没发出去。
所以状态码和解析失败都在 `解析返回体` 里翻成 `接口错误`。
"""

import pytest

from atpy.bili import 接口错误, 解析返回体


def test_正常_json_原样返回():
    载荷 = 解析返回体('{"code": 0, "data": {"bvid": "BV1"}}', 200, "/view")
    assert 载荷["code"] == 0
    assert 载荷["data"]["bvid"] == "BV1"


def test_412_报风控():
    with pytest.raises(接口错误) as 捕获:
        解析返回体("<html>拦截</html>", 412, "/view")
    assert "风控" in str(捕获.value)


def test_其它状态码带状态与地址():
    with pytest.raises(接口错误) as 捕获:
        解析返回体("", 502, "/x/web-interface/view")
    assert "502" in str(捕获.value)
    assert "/x/web-interface/view" in str(捕获.value)


def test_非_json_内容报错并回显片段():
    with pytest.raises(接口错误) as 捕获:
        解析返回体("<html><body>验证码</body></html>", 200, "/view")
    消息 = str(捕获.value)
    assert "不是 JSON" in 消息
    assert "<html>" in 消息


def test_空响应体():
    with pytest.raises(接口错误):
        解析返回体("", 200, "/view")


def test_顶层不是对象():
    """有的接口会返回 `[...]`，调用方按 dict 取值会崩，提前拦掉。"""
    with pytest.raises(接口错误) as 捕获:
        解析返回体("[1, 2, 3]", 200, "/view")
    assert "不是对象" in str(捕获.value)
