"""구현 보고 스키마 (SPEC 5.4 ImplementationReport, 운영 규약 1.9).

IMPLEMENT·FIX 단계에서 구현 담당이 커밋을 마친 뒤 출력한다.
PR 본문의 구현 담당 항목(변경 요약, 설계 의도, 확인할 점)이 여기서 나온다.
FIX 단계에서는 리뷰 지적 번호별 대응(responses)을 함께 낸다.
"""

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from bot.schemas._types import Item
from bot.schemas.hiring import HiringProposal

ChangesSummary = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
DesignIntent = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
]


class ResponseAction(StrEnum):
    FIXED = "fixed"
    DECLINED = "declined"

    @property
    def label(self) -> str:
        return "반영" if self is ResponseAction.FIXED else "반영 안 함"


class FindingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    index: int = Field(ge=1)  # 봇이 전달한 지적 번호 (1부터)
    action: ResponseAction
    note: Item


class ImplementationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    changes_summary: ChangesSummary
    design_intent: DesignIntent
    check_points: list[Item] = Field(default_factory=list, max_length=5)
    responses: list[FindingResponse] = Field(default_factory=list, max_length=10)
    # 채용 제안 (운영 규약 1.12). 근거가 있을 때만 붙인다
    hiring_proposal: HiringProposal | None = None

    @model_validator(mode="after")
    def _unique_responses(self) -> Self:
        indexes = [response.index for response in self.responses]
        if len(indexes) != len(set(indexes)):
            raise ValueError("responses의 index가 겹친다. 지적 하나에 대응 하나씩 쓴다")
        return self
