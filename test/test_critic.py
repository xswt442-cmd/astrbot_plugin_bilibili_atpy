from atpy.critic import MAX_LENGTH, build_prompt, clean, is_usable


def test_strips_quotes_and_spaces():
    assert clean("「这也能过审」") == "这也能过审"
    assert clean("  “离谱”  ") == "离谱"


def test_strips_review_prefix():
    assert clean("锐评：这也能过审") == "这也能过审"
    assert clean("吐槽: 什么玩意") == "什么玩意"


def test_keeps_only_first_line():
    assert clean("这不科学\n因为这本来就不是科学") == "这不科学"


def test_truncates_to_max_length():
    assert len(clean("一" * 30)) == MAX_LENGTH


def test_empty_input_returns_empty():
    assert clean("") == ""
    assert clean("   ") == ""
    assert is_usable("") is False


def test_single_char_is_unusable():
    assert is_usable("好") is False
    assert is_usable("好活") is True


def test_prompt_includes_title_and_description():
    text = build_prompt(
        {"标题": "手搓核聚变", "up主": "老王", "分区": "生活", "播放": 1234, "简介": "用微波炉"}
    )
    assert "手搓核聚变" in text
    assert "老王" in text
    assert "用微波炉" in text


def test_prompt_without_description_has_no_empty_line():
    text = build_prompt({"标题": "x", "up主": "y", "分区": "z", "播放": 0})
    assert "简介" not in text
