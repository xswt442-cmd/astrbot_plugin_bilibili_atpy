from atpy.critic import 可用, 字数上限, 拼提示词, 清洗


def test_去掉引号与前后空白():
    assert 清洗("「这也能过审」") == "这也能过审"
    assert 清洗("  “离谱”  ") == "离谱"


def test_去掉锐评前缀():
    assert 清洗("锐评：这也能过审") == "这也能过审"
    assert 清洗("吐槽: 什么玩意") == "什么玩意"


def test_只取第一行():
    assert 清洗("这不科学\n因为这本来就不是科学") == "这不科学"


def test_超长按字数截断():
    assert len(清洗("一" * 30)) == 字数上限


def test_空输入返回空():
    assert 清洗("") == ""
    assert 清洗("   ") == ""
    assert 可用("") is False


def test_单字评语判为不可用():
    assert 可用("好") is False
    assert 可用("好活") is True


def test_提示词带上标题与简介():
    文本 = 拼提示词(
        {"标题": "手搓核聚变", "up主": "老王", "分区": "生活", "播放": 1234, "简介": "用微波炉"}
    )
    assert "手搓核聚变" in 文本
    assert "老王" in 文本
    assert "用微波炉" in 文本


def test_提示词没有简介也不留空行():
    文本 = 拼提示词({"标题": "x", "up主": "y", "分区": "z", "播放": 0})
    assert "简介" not in 文本
