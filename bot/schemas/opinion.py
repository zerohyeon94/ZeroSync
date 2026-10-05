"""의견 스키마 (운영 규약 2.2).

OPINIONS·DEBATE 단계에서 Beta(Claude)와 Alpha(Codex)가 출력하는 형식이다.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from bot.schemas._types import Item

# 결론은 한 줄 (줄바꿈 금지)
Conclusion = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120, pattern=r"^[^\r\n]+$"),
]
Proposal = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class Stance(StrEnum):
    AGREE = "agree"
    CONDITIONAL = "conditional"
    OPPOSE = "oppose"
    ALTERNATIVE = "alternative"

    @property
    def label(self) -> str:
        return _STANCE_LABELS[self]


_STANCE_LABELS = {
    Stance.AGREE: "찬성",
    Stance.CONDITIONAL: "조건부 찬성",
    Stance.OPPOSE: "반대",
    Stance.ALTERNATIVE: "대안 제시",
}


class Opinion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stance: Stance
    conclusion: Conclusion
    reasons: list[Item] = Field(min_length=1, max_length=4)
    # 찬성이어도 위험은 최소 1개 (AI가 찬성 시 단점을 생략하는 경향 방지)
    risks: list[Item] = Field(min_length=1, max_length=3)
    proposal: Proposal
