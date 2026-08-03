"""护栏输出解析：JSON / fenced / 乱码 fail-open。"""

from airline.guardrails import JailbreakOutput, RelevanceOutput, _parse_guardrail_output


def test_valid_json():
    out = _parse_guardrail_output('{"reasoning":"相关","is_relevant":true}', RelevanceOutput)
    assert out.is_relevant is True


def test_fenced_json():
    out = _parse_guardrail_output('```json\n{"reasoning":"x","is_safe":false}\n```', JailbreakOutput)
    assert out.is_safe is False


def test_garbage_fails_open():
    assert _parse_guardrail_output("完全不是JSON", RelevanceOutput).is_relevant is True
    assert _parse_guardrail_output("乱码", JailbreakOutput).is_safe is True


def test_explicit_false_preserved():
    out = _parse_guardrail_output('{"reasoning":"越狱","is_safe":false}', JailbreakOutput)
    assert out.is_safe is False
