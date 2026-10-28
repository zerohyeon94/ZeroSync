"""채용 제안 스키마 (운영 규약 1.12, SPEC 5.4, Q19).

팀장은 단계 보고 JSON의 선택 필드 `hiring_proposal`로 새 팀·팀원을 제안한다.
제안만 하고 팀이나 역할을 만들지 않는다. 숫자 근거(실패 수 등)는 봇이 DB에서 계산해 붙인다.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from bot.schemas._types import Item

Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class HiringKind(StrEnum):
    TEAM = "team"  # 새 팀
    MEMBER = "member"  # 기존 팀의 팀원

    @property
    def label(self) -> str:
        return {HiringKind.TEAM: "새 팀", HiringKind.MEMBER: "팀원"}[self]


class HiringProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: HiringKind
    team: Short  # 새 팀 이름 또는 팀원을 둘 팀
    role: Short  # 맡길 역할 (예: 디자인팀장, 구현 담당)
    reason: Reason  # 어떤 작업에서 무엇이 부족했는가
    cases: list[Item] = Field(min_length=1, max_length=5)  # 근거가 된 작업
    duties: Item  # 맡길 업무
    mbti: str = Field(default="", pattern=r"^([EI][NS][FT][JP])?$")
    competencies: list[Item] = Field(min_length=1, max_length=5)
    if_not_hired: Item  # 채용하지 않을 때의 영향
