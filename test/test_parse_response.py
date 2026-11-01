"""响应体解析的收口逻辑。

线上崩过一次：风控返回 412 的 HTML，`响应.json()` 抛 `JSONDecodeError`，
而 `_补简介` 只捕 `接口错误`，异常一路冒到调度循环，整轮评论没发出去。
所以状态码和解析失败都在 `解析返回体` 里翻成 `接口错误`。
"""

import pytest

from atpy.bili import ApiError, parse_response


def test_valid_json_returned_as_is():
    payload = parse_response('{"code": 0, "data": {"bvid": "BV1"}}', 200, "/view")
    assert payload["code"] == 0
    assert payload["data"]["bvid"] == "BV1"


def test_412_reports_risk_control():
    with pytest.raises(ApiError) as caught:
        parse_response("<html>拦截</html>", 412, "/view")
    assert "风控" in str(caught.value)


def test_other_status_includes_code_and_url():
    with pytest.raises(ApiError) as caught:
        parse_response("", 502, "/x/web-interface/view")
    assert "502" in str(caught.value)
    assert "/x/web-interface/view" in str(caught.value)


def test_non_json_raises_with_snippet():
    with pytest.raises(ApiError) as caught:
        parse_response("<html><body>验证码</body></html>", 200, "/view")
    message = str(caught.value)
    assert "不是 JSON" in message
    assert "<html>" in message


def test_empty_body():
    with pytest.raises(ApiError):
        parse_response("", 200, "/view")


def test_top_level_not_object():
    """有的接口会返回 `[...]`，调用方按 dict 取值会崩，提前拦掉。"""
    with pytest.raises(ApiError) as caught:
        parse_response("[1, 2, 3]", 200, "/view")
    assert "不是对象" in str(caught.value)
