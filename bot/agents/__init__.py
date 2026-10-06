"""에이전트 호출 계층 (SPEC 5).

CLI 러너(ClaudeCliRunner, CodexCliRunner)는 CLI 옵션 확인(SPEC 10장 V1~V3) 후 추가한다.
"""

from bot.agents.base import (
    AgentName,
    AgentRequest,
    AgentResult,
    AgentRunner,
    Mode,
    RunStatus,
    Stage,
)
from bot.agents.fake import FakeAgentRunner
from bot.agents.process import ProcessResult, ProcessRunner

__all__ = [
    "AgentName",
    "AgentRequest",
    "AgentResult",
    "AgentRunner",
    "FakeAgentRunner",
    "Mode",
    "ProcessResult",
    "ProcessRunner",
    "RunStatus",
    "Stage",
]
