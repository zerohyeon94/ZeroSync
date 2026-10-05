"""리뷰 판정 스키마 (운영 규약 2.3).

REVIEW 단계에서 Alpha(Codex)가 출력하는 형식이다.
판정과 지적 등급이 어긋나면 검증 단계에서 형식 오류로 처리한다.
"""

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from bot.schemas._types import Item

Summary = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class Verdict(StrEnum):
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"


class Severity(StrEnum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"

    @property
    def label(self) -> str:
        return _SEVERITY_LABELS[self]


_SEVERITY_LABELS = {
    Severity.REQUIRED: "[필수]",
    Severity.RECOMMENDED: "[권장]",
}


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: Severity
    # 설계 문제처럼 특정 위치가 없는 지적은 file·line을 비운다
    file: Item | None = None
    line: int | None = Field(default=None, ge=1)
    problem: Item
    reason: Item
    suggestion: Item

    @model_validator(mode="after")
    def _line_requires_file(self) -> Self:
        if self.line is not None and self.file is None:
            raise ValueError("line을 쓰려면 file도 있어야 한다")
        return self


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: Verdict
    summary: Summary
    findings: list[Finding] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _verdict_matches_findings(self) -> Self:
        expected = Verdict.CHANGES_REQUESTED if self.required_findings else Verdict.APPROVED
        if self.verdict != expected:
            raise ValueError(
                f"verdict가 {self.verdict}이지만 [필수] 지적 {len(self.required_findings)}개에 "
                f"맞는 판정은 {expected}이다"
            )
        return self

    @property
    def required_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.REQUIRED]

    @property
    def recommended_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.RECOMMENDED]
