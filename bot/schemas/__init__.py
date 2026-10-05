"""에이전트 출력 스키마.

에이전트는 이 스키마의 JSON으로 출력하고, 봇은 검증한 원본을 저장·표시·옮겨 적기에 그대로 쓴다.
"""

from bot.schemas.extract import AgentOutputError, extract_json, parse_agent_output
from bot.schemas.opinion import Opinion, Stance
from bot.schemas.review import Finding, Review, Severity, Verdict

__all__ = [
    "AgentOutputError",
    "Finding",
    "Opinion",
    "Review",
    "Severity",
    "Stance",
    "Verdict",
    "extract_json",
    "parse_agent_output",
]
