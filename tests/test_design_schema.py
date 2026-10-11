import json

import pytest
from pydantic import ValidationError

from bot.schemas import (
    FEATURE_NAMES,
    ISSUE_NUMBER,
    AgentOutputError,
    ChangeType,
    DesignSummary,
    ImplementationReport,
    parse_agent_output,
)

FEATURES = {"예산 배너", "지출 기록"}


def design_data(**overrides):
    data = {
        "change_type": "feature_change",
        "target_feature": "예산 배너",
        "slug": "budget-banner",
        "title": "월 예산 초과 시 홈 화면 배너 표시",
        "scope": "budget",
        "summary": "홈 화면에 초과 배너를 띄운다",
        "changes": ["HomeView에 배너 추가"],
        "test_plan": ["초과·미초과 경계 테스트"],
        "risks": [],
        "design_doc": "docs/설계/42-budget-banner.md",
    }
    data.update(overrides)
    if "slug" in overrides and "design_doc" not in overrides:
        data["design_doc"] = f"docs/설계/42-{overrides['slug']}.md"
    return data


def validate(data, features=FEATURES):
    context = None if features is None else {FEATURE_NAMES: features}
    return DesignSummary.model_validate(data, context=context)


# change_type (운영 규약 3.8, 4.2)


@pytest.mark.parametrize(
    ("value", "label", "branch_type"),
    [
        ("feature_add", "기능 추가", "feat"),
        ("feature_change", "기능 변경", "feat"),
        ("bug_fix", "버그 수정", "fix"),
        ("internal", "내부 개선", "refactor"),
    ],
)
def test_change_type_labels_and_branch_types(value, label, branch_type):
    change_type = ChangeType(value)
    assert change_type.label == label
    assert change_type.branch_type == branch_type


def test_rejects_unknown_change_type():
    with pytest.raises(ValidationError):
        validate(design_data(change_type="기능 변경"))


# target_feature (운영 규약 3.8)


def test_existing_feature_is_accepted_for_change():
    assert validate(design_data()).target_feature == "예산 배너"


def test_md_extension_is_stripped():
    assert validate(design_data(target_feature="예산 배너.md")).target_feature == "예산 배너"


@pytest.mark.parametrize("change_type", ["feature_change", "bug_fix", "internal"])
def test_non_add_requires_existing_feature(change_type):
    with pytest.raises(ValidationError, match="기능/ 폴더에 없다"):
        validate(design_data(change_type=change_type, target_feature="없는 기능"))


def test_feature_add_requires_new_feature_name():
    assert validate(design_data(change_type="feature_add", target_feature="월간 리포트"))
    with pytest.raises(ValidationError, match="이미 기능/ 폴더에 있다"):
        validate(design_data(change_type="feature_add", target_feature="예산 배너"))


def test_without_context_only_format_is_checked():
    assert validate(design_data(target_feature="아무 이름"), features=None)


@pytest.mark.parametrize("name", ["", "   ", "기능/예산 배너", "a\\b", "첫 줄\n둘째 줄"])
def test_rejects_invalid_feature_names(name):
    with pytest.raises(ValidationError):
        validate(design_data(target_feature=name), features=None)


# slug (운영 규약 4.2)


@pytest.mark.parametrize("slug", ["budget", "budget-banner", "a-b-c-d-e", "v2-fix", "x" * 40])
def test_accepts_valid_slugs(slug):
    assert validate(design_data(slug=slug)).slug == slug


@pytest.mark.parametrize(
    "slug",
    ["", "Budget", "budget_banner", "-budget", "budget-", "budget--banner"]
    + ["a-b-c-d-e-f", "x" * 41],
)
def test_rejects_invalid_slugs(slug):
    with pytest.raises(ValidationError):
        validate(design_data(slug=slug))


# 브랜치 이름 (운영 규약 4.2, 4.7)


@pytest.mark.parametrize(
    ("change_type", "target", "expected"),
    [
        ("feature_add", "월간 리포트", "feat/42-budget-banner"),
        ("feature_change", "예산 배너", "feat/42-budget-banner"),
        ("bug_fix", "예산 배너", "fix/42-budget-banner"),
        ("internal", "예산 배너", "refactor/42-budget-banner"),
    ],
)
def test_branch_name(change_type, target, expected):
    design = validate(design_data(change_type=change_type, target_feature=target))
    assert design.branch_name(42) == expected


def test_branch_name_requires_positive_issue_number():
    with pytest.raises(ValueError, match="Issue 번호"):
        validate(design_data()).branch_name(0)


# 에이전트 응답 파싱


def test_parse_agent_output_passes_feature_context():
    payload = json.dumps(design_data(target_feature="없는 기능"), ensure_ascii=False)
    text = f"```json\n{payload}\n```"
    with pytest.raises(AgentOutputError, match="기능/ 폴더에 없다"):
        parse_agent_output(text, DesignSummary, context={FEATURE_NAMES: FEATURES})
    assert parse_agent_output(text, DesignSummary).target_feature == "없는 기능"


# SPEC 5.4 추가 필드 (Q1)


def test_full_design_summary_and_conventional_title():
    summary = validate(design_data())
    assert summary.conventional_title == "feat(budget): 월 예산 초과 시 홈 화면 배너 표시"
    no_scope = validate(design_data(scope=None, change_type="bug_fix"))
    assert no_scope.conventional_title == "fix: 월 예산 초과 시 홈 화면 배너 표시"


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": "두 줄\n제목"},
        {"title": "가" * 81},
        {"scope": "Budget"},
        {"summary": "가" * 501},
        {"changes": []},
        {"changes": ["가"] * 9},
        {"test_plan": []},
        {"risks": ["가"] * 4},
        {"design_doc": "docs/42-budget-banner.md"},
        {"design_doc": "docs/설계/42-other-name.md"},
    ],
)
def test_rejects_invalid_added_fields(overrides):
    with pytest.raises(ValidationError):
        validate(design_data(**overrides))


def test_design_doc_must_match_issue_number_from_context():
    data = design_data()
    context = {FEATURE_NAMES: FEATURES, ISSUE_NUMBER: 42}
    assert DesignSummary.model_validate(data, context=context).design_doc.endswith(
        "42-budget-banner.md"
    )
    with pytest.raises(ValidationError, match="docs/설계/7-budget-banner.md"):
        DesignSummary.model_validate(data, context={ISSUE_NUMBER: 7})


# 구현 보고


def test_implementation_report():
    report = ImplementationReport.model_validate(
        {
            "changes_summary": "배너 추가",
            "design_intent": "홈에서 바로 보이게",
            "check_points": ["경계 시각"],
            "responses": [
                {"index": 1, "action": "fixed", "note": "고쳤다"},
                {"index": 2, "action": "declined", "note": "범위 밖"},
            ],
        }
    )
    assert [r.action.label for r in report.responses] == ["반영", "반영 안 함"]
    with pytest.raises(ValidationError, match="겹친다"):
        ImplementationReport.model_validate(
            {
                "changes_summary": "a",
                "design_intent": "b",
                "responses": [
                    {"index": 1, "action": "fixed", "note": "x"},
                    {"index": 1, "action": "declined", "note": "y"},
                ],
            }
        )
    with pytest.raises(ValidationError):
        ImplementationReport.model_validate({"changes_summary": "", "design_intent": "b"})
