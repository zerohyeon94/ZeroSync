"""스키마 공통 문자열 타입."""

from typing import Annotated

from pydantic import StringConstraints

# 목록 항목 하나(근거, 위험, 지적 내용)의 길이 제한.
# 게시용 요약 1,500자(운영 규약 2.6)를 지키기 위한 값
ITEM_MAX_LENGTH = 200

Item = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=ITEM_MAX_LENGTH)
]
