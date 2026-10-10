"""작업 상태와 전이 규칙 (SPEC 3).

전이는 I/O 없는 순수 함수다: (현재 작업, 이벤트) → (다음 상태, 실행할 효과, 바꿀 필드).
효과는 무엇을 해야 하는지만 나타내고, 실제 실행(에이전트 호출, GitHub, 볼트, 게시)은 엔진이 한다.

현재 구현 범위: 작업 생성, OPINIONS 단계의 전이, 모든 상태의 /stop.
그 밖의 상태에서 허용된 명령은 이후 스레드에서 구현하며, 지금은 NotImplementedError를 던진다.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from bot.agents.base import AgentName

# 질문 수가 이 값을 넘는 순간 "/decide 대기 중"을 1회 알린다 (운영 규약 1.6)
OPINION_NOTICE_AFTER = 5

BOTH_AGENTS: tuple[AgentName, ...] = ("claude", "codex")


class TaskState(StrEnum):
    OPINIONS = "OPINIONS"
    DESIGNING = "DESIGNING"
    AWAIT_DESIGN_APPROVAL = "AWAIT_DESIGN_APPROVAL"
    IMPLEMENTING = "IMPLEMENTING"
    TESTING = "TESTING"
    REVIEWING = "REVIEWING"
    FIXING = "FIXING"
    AWAIT_MERGE = "AWAIT_MERGE"
    DOC_DRAFTING = "DOC_DRAFTING"
    AWAIT_DOC_APPROVAL = "AWAIT_DOC_APPROVAL"
    DONE = "DONE"
    STOPPED = "STOPPED"
    NEEDS_HUMAN = "NEEDS_HUMAN"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL

    @property
    def waits_for_zero(self) -> bool:
        """Zero 대기 상태. 멘션·재멘션 대상이다 (운영 규약 2.5)."""
        return self in _WAITING


_TERMINAL = frozenset({TaskState.DONE, TaskState.STOPPED})
_WAITING = frozenset(
    {
        TaskState.OPINIONS,
        TaskState.AWAIT_DESIGN_APPROVAL,
        TaskState.AWAIT_MERGE,
        TaskState.AWAIT_DOC_APPROVAL,
        TaskState.NEEDS_HUMAN,
    }
)


class CommandName(StrEnum):
    """상태를 바꿀 수 있는 명령. /status, /ping은 상태와 무관해 전이 대상이 아니다."""

    DEBATE = "debate"
    DECIDE = "decide"
    APPROVE = "approve"
    REVISE = "revise"
    SKIP = "skip"
    FIX = "fix"
    STOP = "stop"
    RESUME = "resume"


# 상태별 허용 명령 (SPEC 4장). /stop은 종료 상태 외 전부
ALLOWED_COMMANDS: Mapping[TaskState, frozenset[CommandName]] = {
    state: frozenset({CommandName.STOP}) if not state.is_terminal else frozenset()
    for state in TaskState
} | {
    TaskState.OPINIONS: frozenset({CommandName.DEBATE, CommandName.DECIDE, CommandName.STOP}),
    TaskState.AWAIT_DESIGN_APPROVAL: frozenset(
        {CommandName.APPROVE, CommandName.REVISE, CommandName.STOP}
    ),
    TaskState.AWAIT_MERGE: frozenset({CommandName.FIX, CommandName.STOP}),
    TaskState.AWAIT_DOC_APPROVAL: frozenset(
        {CommandName.APPROVE, CommandName.REVISE, CommandName.SKIP, CommandName.STOP}
    ),
    TaskState.NEEDS_HUMAN: frozenset({CommandName.RESUME, CommandName.STOP}),
}


# 이벤트


@dataclass(frozen=True)
class PostCreated:
    """Zero가 포럼에 게시글을 올렸다. 작업이 생성된다."""

    title: str
    text: str


@dataclass(frozen=True)
class ZeroMessage:
    """게시글 안의 Zero 일반 메시지. `@claude`/`@codex`로 시작하면 지정된 쪽만 응답한다."""

    text: str


@dataclass(frozen=True)
class Command:
    name: CommandName
    arg: str = ""


Event = ZeroMessage | Command


# 효과


@dataclass(frozen=True)
class RequestOpinions:
    """에이전트에게 의견을 요청한다.

    with_history=False면 첫 의견: 상대 의견을 보지 않고 독립 작성.
    True면 게시글 전체 흐름을 함께 전달한다 (운영 규약 1.6).
    """

    agents: tuple[AgentName, ...]
    question: str
    with_history: bool


@dataclass(frozen=True)
class RequestDebate:
    """두 에이전트에게 상대 의견에 대한 반박을 1회씩 요청한다."""


@dataclass(frozen=True)
class CreateIssue:
    """Zero의 /decide 원문으로 GitHub Issue를 만든다 (운영 규약 1.8)."""

    decision: str


@dataclass(frozen=True)
class WriteVaultDecision:
    """볼트에 결정 노트와 논의 목록 행을 쓴다 (운영 규약 3.5)."""

    decision: str


@dataclass(frozen=True)
class StartDesign:
    """Beta에게 설계를 요청한다."""

    decision: str


@dataclass(frozen=True)
class CancelAgentRuns:
    """이 작업에서 실행 중인 CLI를 모두 종료한다."""


class NoticeCode(StrEnum):
    AWAITING_DECISION = "awaiting_decision"
    STOPPED = "stopped"
    REJECTED = "rejected"
    # 아래는 전이가 아니라 엔진이 효과를 실행하면서 남기는 안내다
    DECISION_RECORDED = "decision_recorded"
    AGENT_FAILED = "agent_failed"
    NOT_IMPLEMENTED = "not_implemented"


@dataclass(frozen=True)
class PostNotice:
    """[ZeroSync] 이름으로 게시글에 짧은 안내를 남긴다."""

    code: NoticeCode
    detail: str = ""


Effect = (
    RequestOpinions
    | RequestDebate
    | CreateIssue
    | WriteVaultDecision
    | StartDesign
    | CancelAgentRuns
    | PostNotice
)


@dataclass(frozen=True)
class Transition:
    state: TaskState
    effects: tuple[Effect, ...] = ()
    # 함께 저장할 tasks 필드 (예: opinion_rounds)
    updates: Mapping[str, object] = field(default_factory=dict)


class TaskView(Protocol):
    @property
    def state(self) -> TaskState: ...

    @property
    def opinion_rounds(self) -> int: ...


# 전이


def start_task(event: PostCreated) -> Transition:
    """게시글 작성 → OPINIONS. 두 에이전트에게 독립된 첫 의견을 요청한다."""
    return Transition(
        TaskState.OPINIONS,
        (RequestOpinions(BOTH_AGENTS, event.text, with_history=False),),
        {"opinion_rounds": 0},
    )


def transition(task: TaskView, event: Event) -> Transition:
    state = task.state
    if isinstance(event, Command) and event.name is CommandName.STOP:
        if state.is_terminal:
            return _reject(state, "이미 끝난 작업이다")
        return Transition(TaskState.STOPPED, (CancelAgentRuns(), PostNotice(NoticeCode.STOPPED)))
    if state is TaskState.OPINIONS:
        return _opinions(task, event)
    if isinstance(event, Command) and event.name in ALLOWED_COMMANDS[state]:
        raise NotImplementedError(f"{state}의 /{event.name} 전이는 아직 구현하지 않았다")
    return _reject(state)


def _opinions(task: TaskView, event: Event) -> Transition:
    state = TaskState.OPINIONS
    if isinstance(event, ZeroMessage):
        agents, question = _parse_target(event.text)
        rounds = task.opinion_rounds + 1
        effects: list[Effect] = [RequestOpinions(agents, question, with_history=True)]
        if rounds == OPINION_NOTICE_AFTER + 1:
            effects.append(PostNotice(NoticeCode.AWAITING_DECISION))
        return Transition(state, tuple(effects), {"opinion_rounds": rounds})

    if event.name is CommandName.DEBATE:
        return Transition(state, (RequestDebate(),))
    if event.name is CommandName.DECIDE:
        decision = event.arg.strip()
        if not decision:
            return _reject(state, "/decide 뒤에 방향을 적어야 한다")
        return Transition(
            TaskState.DESIGNING,
            (CreateIssue(decision), WriteVaultDecision(decision), StartDesign(decision)),
        )
    return _reject(state)


def _parse_target(text: str) -> tuple[tuple[AgentName, ...], str]:
    stripped = text.lstrip()
    for agent in BOTH_AGENTS:
        prefix = f"@{agent}"
        if stripped.lower().startswith(prefix):
            rest = stripped[len(prefix) :]
            # "@claudette"처럼 이름이 이어지면 지정으로 보지 않는다
            if not rest or rest[0].isspace():
                return (agent,), rest.strip()
    return BOTH_AGENTS, text.strip()


def _reject(state: TaskState, reason: str = "") -> Transition:
    allowed = sorted(f"/{name}" for name in ALLOWED_COMMANDS[state])
    detail = f"현재 상태: {state}. 가능한 명령: {', '.join(allowed) or '없음'}"
    if state is TaskState.OPINIONS:
        detail += ", 일반 메시지"
    if reason:
        detail = f"{reason}. {detail}"
    return Transition(state, (PostNotice(NoticeCode.REJECTED, detail),))
