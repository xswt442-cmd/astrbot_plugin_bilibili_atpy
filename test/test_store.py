import json

from atpy.store import MAX_KEPT, RecordBook


def test_append_then_read_back(tmp_path):
    book = RecordBook(tmp_path)
    book.append({"bvid": "BV1", "标题": "标题", "锐评": "好活"})
    records = book.all_records()
    assert len(records) == 1
    assert records[0]["bvid"] == "BV1"
    assert records[0]["时间"] > 0


def test_sent_bvids_cover_all_history(tmp_path):
    book = RecordBook(tmp_path)
    book.append({"bvid": "BV1"})
    book.append({"bvid": "BV2"})
    assert book.sent_bvids() == {"BV1", "BV2"}


def test_recent_returns_newest_first(tmp_path):
    book = RecordBook(tmp_path)
    for i in range(3):
        book.append({"bvid": f"BV{i}", "时间": 100 + i})
    assert [item["bvid"] for item in book.recent(2)] == ["BV2", "BV1"]


def test_keeps_newest_up_to_limit(tmp_path):
    book = RecordBook(tmp_path)
    for i in range(MAX_KEPT + 5):
        book.append({"bvid": f"BV{i}", "时间": i})
    records = book.all_records()
    assert len(records) == MAX_KEPT
    assert records[0]["bvid"] == "BV5"


def test_schedule_valid_for_day_only(tmp_path):
    book = RecordBook(tmp_path)
    book.set_schedule("2026-10-21", [1, 2, 3])
    assert book.get_schedule("2026-10-21") == [1, 2, 3]
    assert book.get_schedule("2026-10-22") is None


def test_empty_schedule_is_not_missing(tmp_path):
    book = RecordBook(tmp_path)
    book.set_schedule("2026-10-21", [])
    assert book.get_schedule("2026-10-21") == []


def test_broken_file_backed_up(tmp_path):
    path = tmp_path / "history.json"
    path.write_text("{ 这不是 json", encoding="utf-8")
    book = RecordBook(tmp_path)
    assert book.all_records() == []
    assert list(tmp_path.glob("history.坏-*.json"))


def test_write_is_complete_json(tmp_path):
    book = RecordBook(tmp_path)
    book.append({"bvid": "BV1", "标题": "带中文的标题"})
    raw = (tmp_path / "history.json").read_text(encoding="utf-8")
    assert json.loads(raw)["记录"][0]["标题"] == "带中文的标题"
    assert not list(tmp_path.glob("*.临时"))
