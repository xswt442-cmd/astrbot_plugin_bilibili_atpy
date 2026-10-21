import json

from atpy.store import 保留条数, 记录簿


def test_追加后能读回(tmp_path):
    簿 = 记录簿(tmp_path)
    簿.追加({"bvid": "BV1", "标题": "标题", "锐评": "好活"})
    记录 = 簿.全部()
    assert len(记录) == 1
    assert 记录[0]["bvid"] == "BV1"
    assert 记录[0]["时间"] > 0


def test_已发过的是全部历史(tmp_path):
    簿 = 记录簿(tmp_path)
    簿.追加({"bvid": "BV1"})
    簿.追加({"bvid": "BV2"})
    assert 簿.已发过的() == {"BV1", "BV2"}


def test_最近按新到旧(tmp_path):
    簿 = 记录簿(tmp_path)
    for 序 in range(3):
        簿.追加({"bvid": f"BV{序}", "时间": 100 + 序})
    assert [条["bvid"] for 条 in 簿.最近(2)] == ["BV2", "BV1"]


def test_超过上限截掉最旧的(tmp_path):
    簿 = 记录簿(tmp_path)
    for 序 in range(保留条数 + 5):
        簿.追加({"bvid": f"BV{序}", "时间": 序})
    记录 = 簿.全部()
    assert len(记录) == 保留条数
    assert 记录[0]["bvid"] == "BV5"


def test_排期只在当天有效(tmp_path):
    簿 = 记录簿(tmp_path)
    簿.存排期("2026-10-21", [1, 2, 3])
    assert 簿.取排期("2026-10-21") == [1, 2, 3]
    assert 簿.取排期("2026-10-22") is None


def test_排过但零轮的日期不算没排(tmp_path):
    簿 = 记录簿(tmp_path)
    簿.存排期("2026-10-21", [])
    assert 簿.取排期("2026-10-21") == []


def test_坏文件不炸且留备份(tmp_path):
    路径 = tmp_path / "history.json"
    路径.write_text("{ 这不是 json", encoding="utf-8")
    簿 = 记录簿(tmp_path)
    assert 簿.全部() == []
    assert list(tmp_path.glob("history.坏-*.json"))


def test_写入是完整json(tmp_path):
    簿 = 记录簿(tmp_path)
    簿.追加({"bvid": "BV1", "标题": "带中文的标题"})
    原文 = (tmp_path / "history.json").read_text(encoding="utf-8")
    assert json.loads(原文)["记录"][0]["标题"] == "带中文的标题"
    assert not list(tmp_path.glob("*.临时"))
