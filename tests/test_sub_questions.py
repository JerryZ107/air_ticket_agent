"""复合问题拆分逻辑（RAG 多主题召回）。"""

from rag.text_utils import split_sub_questions


def test_compound_question_split():
    parts = split_sub_questions("行李额度是多少？如果延误3小时以上有什么餐券？")
    assert parts == ["行李额度是多少", "如果延误3小时以上有什么餐券"]


def test_single_question_unchanged():
    assert split_sub_questions("退票政策是什么") == ["退票政策是什么"]


def test_semicolon_and_period():
    assert split_sub_questions("查一下订单；再看看航班状态。") == [
        "查一下订单",
        "再看看航班状态",
    ]


def test_empty_falls_back_to_raw():
    assert split_sub_questions("") == [""]
