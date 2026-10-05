import json

import pytest
from pydantic import ValidationError

from bot.schemas import (
    AgentOutputError,
    Opinion,
    Review,
    Severity,
    Stance,
    Verdict,
    extract_json,
    parse_agent_output,
)


def opinion_data(**overrides):
    data = {
        "stance": "agree",
        "conclusion": "월 예산 배너를 홈 화면에 추가한다",
        "reasons": ["사용자가 초과 사실을 바로 본다"],
        "risks": ["배너가 다른 알림을 가린다"],
        "proposal": "초과 시에만 배너를 띄운다",
    }
    data.update(overrides)
    return data


def finding_data(severity="required", **overrides):
    data = {
        "severity": severity,
        "file": "Budget/BudgetStore.swift",
        "line": 42,
        "problem": "월 경계에서 합계가 0이 된다",
        "reason": "시간대를 UTC로 계산한다",
        "suggestion": "Calendar.current 기준으로 월 시작을 구한다",
    }
    data.update(overrides)
    return data


def review_data(verdict, findings):
    return {"verdict": verdict, "summary": "월 경계 처리 확인", "findings": findings}


# 의견 (운영 규약 2.2)


def test_opinion_accepts_valid_data():
    opinion = Opinion.model_validate(opinion_data())
    assert opinion.stance is Stance.AGREE
    assert opinion.stance.label == "찬성"


@pytest.mark.parametrize("stance", ["agree", "conditional", "oppose", "alternative"])
def test_opinion_accepts_four_stances(stance):
    assert Opinion.model_validate(opinion_data(stance=stance)).stance == stance


def test_opinion_rejects_unknown_stance():
    with pytest.raises(ValidationError):
        Opinion.model_validate(opinion_data(stance="찬성"))


def test_opinion_requires_at_least_one_risk_even_when_agreeing():
    with pytest.raises(ValidationError):
        Opinion.model_validate(opinion_data(stance="agree", risks=[]))


@pytest.mark.parametrize(
    ("field", "count", "ok"),
    [("reasons", 4, True), ("reasons", 5, False), ("risks", 3, True), ("risks", 4, False)],
)
def test_opinion_list_limits(field, count, ok):
    data = opinion_data(**{field: ["항목"] * count})
    if ok:
        Opinion.model_validate(data)
    else:
        with pytest.raises(ValidationError):
            Opinion.model_validate(data)


def test_opinion_conclusion_limit_is_120_chars_on_one_line():
    Opinion.model_validate(opinion_data(conclusion="가" * 120))
    with pytest.raises(ValidationError):
        Opinion.model_validate(opinion_data(conclusion="가" * 121))
    with pytest.raises(ValidationError):
        Opinion.model_validate(opinion_data(conclusion="첫 줄\n둘째 줄"))


def test_opinion_proposal_limit_is_300_chars():
    Opinion.model_validate(opinion_data(proposal="가" * 300))
    with pytest.raises(ValidationError):
        Opinion.model_validate(opinion_data(proposal="가" * 301))


def test_opinion_item_limit_is_200_chars():
    Opinion.model_validate(opinion_data(reasons=["가" * 200]))
    with pytest.raises(ValidationError):
        Opinion.model_validate(opinion_data(reasons=["가" * 201]))


def test_opinion_rejects_blank_item_and_extra_field():
    with pytest.raises(ValidationError):
        Opinion.model_validate(opinion_data(risks=["   "]))
    with pytest.raises(ValidationError):
        Opinion.model_validate(opinion_data(question="추가 필드"))


# 리뷰 판정 (운영 규약 2.3)


def test_review_with_required_finding_is_changes_requested():
    review = Review.model_validate(
        review_data("CHANGES_REQUESTED", [finding_data("required"), finding_data("recommended")])
    )
    assert review.verdict is Verdict.CHANGES_REQUESTED
    assert len(review.required_findings) == 1
    assert len(review.recommended_findings) == 1
    assert review.required_findings[0].severity.label == "[필수]"


def test_review_without_required_finding_is_approved():
    review = Review.model_validate(review_data("APPROVED", [finding_data("recommended")]))
    assert review.verdict is Verdict.APPROVED
    assert Review.model_validate(review_data("APPROVED", [])).findings == []


def test_review_rejects_approved_with_required_finding():
    with pytest.raises(ValidationError, match="CHANGES_REQUESTED"):
        Review.model_validate(review_data("APPROVED", [finding_data("required")]))


def test_review_rejects_changes_requested_without_required_finding():
    with pytest.raises(ValidationError, match="APPROVED"):
        Review.model_validate(review_data("CHANGES_REQUESTED", [finding_data("recommended")]))


def test_review_allows_at_most_10_findings():
    Review.model_validate(review_data("APPROVED", [finding_data("recommended")] * 10))
    with pytest.raises(ValidationError):
        Review.model_validate(review_data("APPROVED", [finding_data("recommended")] * 11))


def test_review_summary_limit_is_200_chars():
    data = review_data("APPROVED", [])
    Review.model_validate({**data, "summary": "가" * 200})
    with pytest.raises(ValidationError):
        Review.model_validate({**data, "summary": "가" * 201})


def test_finding_without_location_is_allowed():
    review = Review.model_validate(
        review_data("CHANGES_REQUESTED", [finding_data(file=None, line=None)])
    )
    assert review.findings[0].file is None
    assert review.findings[0].severity is Severity.REQUIRED


def test_finding_line_requires_file_and_must_be_positive():
    with pytest.raises(ValidationError, match="file"):
        Review.model_validate(review_data("CHANGES_REQUESTED", [finding_data(file=None)]))
    with pytest.raises(ValidationError):
        Review.model_validate(review_data("CHANGES_REQUESTED", [finding_data(line=0)]))


# JSON 추출 (운영 규약 2.1)


def test_extract_json_from_code_block():
    text = '의견입니다.\n```json\n{"a": 1}\n```\n끝.'
    assert extract_json(text) == '{"a": 1}'


def test_extract_json_accepts_raw_json():
    assert extract_json('  {"a": 1}\n') == '{"a": 1}'


def test_extract_json_rejects_missing_block():
    with pytest.raises(AgentOutputError, match="찾지 못했다"):
        extract_json("JSON 없이 답했습니다")


def test_extract_json_rejects_multiple_blocks():
    text = '```json\n{"a": 1}\n```\n```json\n{"b": 2}\n```'
    with pytest.raises(AgentOutputError, match="2개"):
        extract_json(text)


def test_parse_agent_output_returns_model():
    text = f"```json\n{json.dumps(opinion_data(), ensure_ascii=False)}\n```"
    assert parse_agent_output(text, Opinion).conclusion == "월 예산 배너를 홈 화면에 추가한다"


def test_parse_agent_output_reports_syntax_error():
    with pytest.raises(AgentOutputError, match="JSON 구문 오류"):
        parse_agent_output('```json\n{"stance": }\n```', Opinion)


def test_parse_agent_output_reports_field_errors_for_retry():
    text = json.dumps(opinion_data(risks=[], stance="maybe"))
    with pytest.raises(AgentOutputError) as exc:
        parse_agent_output(text, Opinion)
    message = str(exc.value)
    assert message.startswith("스키마 검증 실패:")
    assert "- stance:" in message
    assert "- risks:" in message


def test_parse_agent_output_reports_verdict_mismatch():
    text = json.dumps(review_data("APPROVED", [finding_data("required")]))
    with pytest.raises(AgentOutputError, match="CHANGES_REQUESTED"):
        parse_agent_output(text, Review)
