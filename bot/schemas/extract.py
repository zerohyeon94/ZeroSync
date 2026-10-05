"""에이전트 응답에서 JSON을 꺼내 스키마로 검증한다 (운영 규약 2.1).

검증에 실패하면 AgentOutputError를 던진다. 오류 문구는 에이전트에게 1회 재요청할 때 그대로 붙인다.
"""

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

M = TypeVar("M", bound=BaseModel)

_JSON_BLOCK = re.compile(r"```json[ \t]*\r?\n(.*?)```", re.DOTALL)


class AgentOutputError(ValueError):
    """에이전트 출력이 형식에 맞지 않는다."""


def extract_json(text: str) -> str:
    """응답 텍스트에서 JSON 원문을 꺼낸다.

    ```json 코드 블록이 정확히 하나면 그 내용을, 없으면 응답 전체를 JSON 원문으로 본다
    (CLI의 스키마 강제 출력은 코드 블록 없이 JSON만 돌려준다).
    """
    blocks = _JSON_BLOCK.findall(text)
    if len(blocks) > 1:
        raise AgentOutputError(f"JSON 코드 블록이 {len(blocks)}개다. 1개만 출력해야 한다")
    if blocks:
        return blocks[0].strip()
    stripped = text.strip()
    if not stripped.startswith("{"):
        raise AgentOutputError("```json 코드 블록을 찾지 못했다")
    return stripped


def parse_agent_output(text: str, model: type[M], context: dict[str, Any] | None = None) -> M:
    """응답 텍스트를 model로 검증해 돌려준다. 실패하면 AgentOutputError.

    context는 pydantic 검증 컨텍스트로 그대로 넘긴다 (예: 설계 요약의 기능 파일 목록).
    """
    raw = extract_json(text)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise AgentOutputError(f"JSON 구문 오류: {e.msg} (줄 {e.lineno}, 열 {e.colno})") from e
    try:
        return model.model_validate(data, context=context)
    except ValidationError as e:
        raise AgentOutputError(_format_validation_error(e)) from e


def _format_validation_error(error: ValidationError) -> str:
    lines = ["스키마 검증 실패:"]
    for item in error.errors(include_url=False):
        location = ".".join(str(part) for part in item["loc"]) or "(최상위)"
        lines.append(f"- {location}: {item['msg']}")
    return "\n".join(lines)
