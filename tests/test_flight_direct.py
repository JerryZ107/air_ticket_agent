"""航班号提取与状态文案（确定性直连路径）。"""

from pipeline.flight_direct import _FLIGHT_RE, _zh_status


def test_flight_number_adjacent_to_cjk():
    m = _FLIGHT_RE.search("只问一句：航班PA441现在什么状态？不要帮我改签")
    assert m is not None
    assert m.group(1) == "PA441"


def test_flight_number_with_space():
    m = _FLIGHT_RE.search("查询航班 PA500 直飞")
    assert m is not None
    assert m.group(1) == "PA500"


def test_confirmation_number_not_matched():
    assert _FLIGHT_RE.search("帮我查确认号ABC123") is None


def test_zh_status_translation():
    assert "状态：延误" in _zh_status("航班 X（A 至 B） | 状态：delayed | 余票 3")
    assert _zh_status("状态：scheduled") == "状态：计划中（正常）"
    assert _zh_status("状态：unknown-x") == "状态：unknown-x"
