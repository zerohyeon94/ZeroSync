"""설계 요약 스키마 (운영 규약 3.8, 4.2).

DESIGN 단계에서 Beta(Claude)가 출력하는 설계 요약 JSON 중 규약에 정해진 세 필드만 다룬다.
요약 본문 등 나머지 필드는 SPEC.md가 정해지면 추가한다.

target_feature가 실제 `기능/` 폴더의 파일인지는 검증 컨텍스트로 확인한다.

    DesignSummary.model_validate(data, context={FEATURE_NAMES: {"예산 배너", ...}})

컨텍스트가 없으면 형식만 검사한다.
"""

import re
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

# 검증 컨텍스트 키: 대상 프로젝트 `기능/` 폴더의 파일 이름 집합 (확장자 .md 제외)
FEATURE_NAMES = "feature_names"

# 운영 규약 4.7 push 보호 정규식
BRANCH_NAME_PATTERN = re.compile(r"^(feat|fix|refactor)/\d+-[a-z0-9]+(-[a-z0-9]+)*$")

Slug = Annotated[str, StringConstraints(max_length=40, pattern=r"^[a-z0-9]+(-[a-z0-9]+){0,4}$")]
FeatureName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=100, pattern=r"^[^/\\\r\n]+$"
    ),
]


class ChangeType(StrEnum):
    FEATURE_ADD = "feature_add"
    FEATURE_CHANGE = "feature_change"
    BUG_FIX = "bug_fix"
    INTERNAL = "internal"

    @property
    def label(self) -> str:
        return _CHANGE_TYPE_LABELS[self]

    @property
    def branch_type(self) -> str:
        return _BRANCH_TYPES[self]


_CHANGE_TYPE_LABELS = {
    ChangeType.FEATURE_ADD: "기능 추가",
    ChangeType.FEATURE_CHANGE: "기능 변경",
    ChangeType.BUG_FIX: "버그 수정",
    ChangeType.INTERNAL: "내부 개선",
}

_BRANCH_TYPES = {
    ChangeType.FEATURE_ADD: "feat",
    ChangeType.FEATURE_CHANGE: "feat",
    ChangeType.BUG_FIX: "fix",
    ChangeType.INTERNAL: "refactor",
}


class DesignSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    change_type: ChangeType
    target_feature: FeatureName
    slug: Slug

    @field_validator("target_feature")
    @classmethod
    def _strip_md_extension(cls, value: str) -> str:
        return value.removesuffix(".md")

    @model_validator(mode="after")
    def _target_feature_matches_folder(self, info: ValidationInfo) -> Self:
        names = (info.context or {}).get(FEATURE_NAMES)
        if names is None:
            return self
        exists = self.target_feature in names
        # 기능 추가는 새 기능 정의서를 만들고, 나머지는 기존 정의서를 고친다 (운영 규약 3.8, 3.9-4)
        if self.change_type is ChangeType.FEATURE_ADD and exists:
            raise ValueError(
                f"기능 추가인데 '{self.target_feature}'는 이미 기능/ 폴더에 있다. "
                "기능 변경으로 바꾸거나 새 이름을 써야 한다"
            )
        if self.change_type is not ChangeType.FEATURE_ADD and not exists:
            raise ValueError(
                f"'{self.target_feature}'가 기능/ 폴더에 없다. 전달받은 목록의 이름을 써야 한다"
            )
        return self

    def branch_name(self, issue_number: int) -> str:
        """작업 브랜치 이름 `<type>/<Issue번호>-<slug>` (운영 규약 4.2)."""
        if issue_number < 1:
            raise ValueError("Issue 번호는 1 이상이어야 한다")
        name = f"{self.change_type.branch_type}/{issue_number}-{self.slug}"
        if not BRANCH_NAME_PATTERN.fullmatch(name):
            raise ValueError(f"브랜치 이름 '{name}'이 push 보호 형식에 맞지 않는다")
        return name
