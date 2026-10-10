"""에이전트 호출 인터페이스 (SPEC 5.1).

러너는 에이전트를 실행하고 원문을 돌려줄 뿐 출력을 해석하지 않는다.
JSON 추출과 검증은 bot.schemas.parse_agent_output이 한다.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Protocol

AgentName = Literal["claude", "codex"]
Mode = Literal["read_only", "write_worktree"]


class Stage(StrEnum):
    OPINION = "opinion"
    DEBATE = "debate"
    DESIGN = "design"
    IMPLEMENT = "implement"
    FIX = "fix"
    REVIEW = "review"
    DOC_SYNC = "doc_sync"


class RunStatus(StrEnum):
    """러너가 판정하는 실행 결과.

    agent_runs.status(SPEC 8)의 running·invalid_output은 저장 계층과 출력 검증 단계가 정한다.
    """

    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class AgentRequest:
    run_id: str
    task_id: int
    stage: Stage
    prompt: str
    cwd: Path  # 앱 저장소 또는 작업 worktree
    mode: Mode
    timeout_sec: float
    resume_session: str | None = None  # Claude 세션 이어가기 (최적화, 필수 아님)
    # 응답 JSON 스키마. 주면 CLI의 구조화 출력으로 강제한다 (운영 규약 2.1, SPEC 5.2)
    output_schema: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class AgentResult:
    status: RunStatus
    exit_code: int | None  # 프로세스를 띄우지 못했거나 강제 종료되면 None일 수 있다
    stdout: str  # parse_agent_output()에 넘기는 원문
    stderr: str
    session_id: str | None
    duration_sec: float
    log_path: Path


class AgentRunner(Protocol):
    name: AgentName

    async def run(self, request: AgentRequest) -> AgentResult: ...

    async def cancel(self, run_id: str) -> None: ...
