import random
import time

from atpy.pick import 抽关键词, 挑一个, 过滤, 门槛

关 = 门槛(最少播放=2000, 最多播放=500000, 最多几天前=45)


def 造(bvid: str, 播放: int, 标题: str = "一个足够长的标题", 年前天数: float = 1, aid: int = 1):
    return {
        "bvid": bvid,
        "aid": aid,
        "标题": 标题,
        "播放": 播放,
        "发布": int(time.time() - 年前天数 * 86400),
    }


def test_播放量两头都卡():
    候选 = [造("BV1", 100), 造("BV2", 10000), 造("BV3", 900000)]
    留下 = 过滤(候选, 关, set())
    assert [视频["bvid"] for 视频 in 留下] == ["BV2"]


def test_超时的不留():
    候选 = [造("BV老", 10000, 年前天数=60), 造("BV新", 10000, 年前天数=3)]
    留下 = 过滤(候选, 关, set())
    assert [视频["bvid"] for 视频 in 留下] == ["BV新"]


def test_发过的不留():
    候选 = [造("BV1", 10000), 造("BV2", 10000)]
    留下 = 过滤(候选, 关, {"BV1"})
    assert [视频["bvid"] for 视频 in 留下] == ["BV2"]


def test_标题太短与缺aid的不留():
    现在 = int(time.time())
    候选 = [
        造("BV短", 10000, 标题="哦"),
        {"bvid": "BV无aid", "aid": None, "标题": "一个足够长的标题", "播放": 10000, "发布": 现在},
        {"bvid": "", "aid": 3, "标题": "一个足够长的标题", "播放": 10000, "发布": 现在},
    ]
    assert 过滤(候选, 关, set()) == []


def test_没有候选时返回空():
    assert 挑一个(random.Random(1), [], set(), 关) is None
    assert 挑一个(random.Random(1), [造("BV1", 1)], set(), 关) is None


def test_优先从偏冷的一半里挑():
    """播放量排序后只在前半段随机，避免每次都被爆款占掉。"""
    候选 = [造(f"BV{序}", 3000 + 序 * 1000) for 序 in range(10)]
    选中 = {挑一个(random.Random(种子), 候选, set(), 关)["bvid"] for 种子 in range(40)}
    # 后半段（播放量最高的五个）不应该出现
    assert not (选中 & {f"BV{序}" for 序 in range(5, 10)})
    assert 选中


def test_关键词取自池子里():
    随机源 = random.Random(7)
    抽到 = {抽关键词(随机源) for _ in range(30)}
    assert len(抽到) > 3


def test_自定义关键词可用():
    随机源 = random.Random(3)
    抽到 = {抽关键词(随机源, ["微波炉", "洗衣机"]) for _ in range(30)}
    assert 抽到 <= {"微波炉", "洗衣机"}


def test_禁忌标题被挡掉():
    候选 = [
        造("BV广告", 10000, 标题="抖音代孕广告实录"),
        造("BV正常", 10000, 标题="手搓一个会走路的洗衣机"),
    ]
    留下 = 过滤(候选, 关, set())
    assert [视频["bvid"] for 视频 in 留下] == ["BV正常"]
