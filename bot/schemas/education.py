"""교육 부서 출력 스키마 (ADR-009).

교육팀장은 개념 노트 본문만 JSON으로 낸다. 파일 경로, 제목, 머리말, Daily는 봇이 정한다.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Url = Annotated[str, StringConstraints(max_length=500, pattern=r"^https://\S+$")]


class ConceptNote(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # `## 한 문장으로`부터 끝까지의 마크다운. 형식은 bot.education.note.check_note가 본다
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=200, max_length=20000)]
    # 사실을 확인한 공식 문서·표준·신뢰할 수 있는 자료. #교육 알림에 붙는다
    sources: list[Url] = Field(min_length=1, max_length=8)
    # 확인하지 못해 노트에 "확인하지 못함"으로 적은 것
    unverified: list[Annotated[str, StringConstraints(max_length=200)]] = Field(
        default_factory=list, max_length=5
    )
