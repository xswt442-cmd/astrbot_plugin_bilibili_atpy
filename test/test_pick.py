import random
import time
from datetime import date

from atpy.pick import (
    KEYWORD_POOL,
    Threshold,
    category_for_date,
    filter_candidates,
    pick_keyword,
    pick_one,
)

limits = Threshold(min_play=2000, max_play=500000, max_days_old=45)


def make_video(
    bvid: str, plays: int, title: str = "一个足够长的标题", days_ago: float = 1, aid: int = 1
):
    return {
        "bvid": bvid,
        "aid": aid,
        "标题": title,
        "播放": plays,
        "发布": int(time.time() - days_ago * 86400),
    }


def test_play_count_bounds():
    candidates = [make_video("BV1", 100), make_video("BV2", 10000), make_video("BV3", 900000)]
    kept = filter_candidates(candidates, limits, set())
    assert [video["bvid"] for video in kept] == ["BV2"]


def test_too_old_dropped():
    candidates = [make_video("BV老", 10000, days_ago=60), make_video("BV新", 10000, days_ago=3)]
    kept = filter_candidates(candidates, limits, set())
    assert [video["bvid"] for video in kept] == ["BV新"]


def test_already_sent_dropped():
    candidates = [make_video("BV1", 10000), make_video("BV2", 10000)]
    kept = filter_candidates(candidates, limits, {"BV1"})
    assert [video["bvid"] for video in kept] == ["BV2"]


def test_short_title_or_missing_aid_dropped():
    now = int(time.time())
    candidates = [
        make_video("BV短", 10000, title="哦"),
        {"bvid": "BV无aid", "aid": None, "标题": "一个足够长的标题", "播放": 10000, "发布": now},
        {"bvid": "", "aid": 3, "标题": "一个足够长的标题", "播放": 10000, "发布": now},
    ]
    assert filter_candidates(candidates, limits, set()) == []


def test_no_candidate_returns_none():
    assert pick_one(random.Random(1), [], set(), limits) is None
    assert pick_one(random.Random(1), [make_video("BV1", 1)], set(), limits) is None


def test_prefers_cooler_half():
    """播放量排序后只在前半段随机，避免每次都被爆款占掉。"""
    candidates = [make_video(f"BV{i}", 3000 + i * 1000) for i in range(10)]
    chosen = {
        pick_one(random.Random(seed), candidates, set(), limits)["bvid"] for seed in range(40)
    }
    # 后半段（播放量最高的五个）不应该出现
    assert not (chosen & {f"BV{i}" for i in range(5, 10)})
    assert chosen


def test_keywords_from_pool():
    rng = random.Random(7)
    picked = {pick_keyword(rng) for _ in range(30)}
    assert len(picked) > 3


def test_custom_keywords_supported():
    rng = random.Random(3)
    picked = {pick_keyword(rng, ["微波炉", "洗衣机"]) for _ in range(30)}
    assert picked <= {"微波炉", "洗衣机"}


def test_category_restricts_keywords():
    """每天轮一类，抽词不能跨到别的类去。"""
    rng = random.Random(11)
    picked = {pick_keyword(rng, category="二游") for _ in range(40)}
    assert picked <= set(KEYWORD_POOL["二游"])


def test_custom_keywords_win_over_category():
    """用户明确写了要搜什么，就不该再掺类别里的词。"""
    rng = random.Random(5)
    assert pick_keyword(rng, ["微波炉"], category="王者荣耀") == "微波炉"


def test_five_categories_rotate_daily():
    """连着五天应该把五类走一遍，不多不少。"""
    start = date(2026, 10, 21)
    five_days = [category_for_date(date.fromordinal(start.toordinal() + i)) for i in range(5)]
    assert len(set(five_days)) == 5
    assert set(five_days) == set(KEYWORD_POOL)


def test_rotation_continues_across_days():
    """隔一天取到的类别，是前一天的下一个。"""
    today = date(2026, 10, 21)
    tomorrow = date(2026, 10, 22)
    categories = list(KEYWORD_POOL)
    index = categories.index(category_for_date(today))
    assert category_for_date(tomorrow) == categories[(index + 1) % len(categories)]


def test_zero_age_limit_keeps_old_videos():
    """老视频也能评，评论区凉了无所谓。"""
    old_video = make_video("BV老片", 50000, days_ago=1200)
    new_video = make_video("BV新片", 50000, days_ago=1)
    loose = Threshold(min_play=10000, max_play=5_000_000, max_days_old=0)
    assert {video["bvid"] for video in filter_candidates([old_video, new_video], loose, set())} == {
        "BV老片",
        "BV新片",
    }


def test_forbidden_titles_dropped():
    candidates = [
        make_video("BV广告", 10000, title="抖音代孕广告实录"),
        make_video("BV正常", 10000, title="手搓一个会走路的洗衣机"),
    ]
    kept = filter_candidates(candidates, limits, set())
    assert [video["bvid"] for video in kept] == ["BV正常"]


def test_novel_and_shortdrama_promos_dropped():
    """`totalrank` 下这类标题混得很凶，点进去是读书广告，锐评它没有意义。"""
    candidates = [
        make_video("BV小说", 50000, title="大夏江湖第一祸害虾仁，凭拳脚医术横行天下"),
        make_video("BV短剧", 50000, title="重生之我在末世当龙王，全集完整"),
        make_video("BV正常", 50000, title="手搓一个会走路的洗衣机"),
    ]
    kept = [video["bvid"] for video in filter_candidates(candidates, limits, set())]
    assert kept == ["BV正常"]


def test_shortdrama_episode_formats_dropped():
    """短剧标题的前缀千变万化，能认的只有「第1-55集」这类格式。"""
    candidates = [
        make_video("BV短剧1", 50000, title="Ai欧腐【皮囊下是深海】第1-55集 超清中字"),
        make_video("BV短剧2", 50000, title="都市奇缘 第1~80集全"),
        make_video("BV正常", 50000, title="深海一万米到底有什么"),
    ]
    kept = [video["bvid"] for video in filter_candidates(candidates, limits, set())]
    assert kept == ["BV正常"]
