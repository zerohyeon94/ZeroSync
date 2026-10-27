"""작업 상태와 전이 규칙 (SPEC 3).

전이는 I/O 없는 순수 함수다: (현재 작업, 이벤트) → (다음 상태, 실행할 효과, 바꿀 필드).
효과는 무엇을 해야 하는지만 나타내고, 실제 실행(에이전트 호출, GitHub, 볼트, 게시)은 엔진이 한다.

현재 구현 범위: 작업 생성부터 merge 감지까지 (Phase 1·2). 엔진이 단계 작업(설계, 구현, 테스트,
리뷰)을 마치면 그 결과를 내부 이벤트로 넣어 다음 상태를 정한다.
문서 반영(DOC_DRAFTING, AWAIT_DOC_APPROVAL)은 Phase 3이며,
그 상태의 명령은 NotImplementedError를 던진다.
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


# 엔진이 넣는 내부 이벤트


@dataclass(frozen=True)
class StageSucceeded:
    """설계·구현·수정 작업이 검증까지 끝났다."""


@dataclass(frozen=True)
class StageFailed:
    """단계 작업이 끝내 실패했다 (형식 오류 반복, CLI 실패, 커밋 규칙 위반 등)."""

    reason: str


@dataclass(frozen=True)
class TestsFinished:
    __test__ = False  # pytest가 테스트 클래스로 모으지 않게

    passed: bool
    environment_error: bool = False  # 테스트를 실행하지 못한 환경 문제 (시뮬레이터 등)
    detail: str = ""


@dataclass(frozen=True)
class ReviewFinished:
    approved: bool


@dataclass(frozen=True)
class PrMerged:
    """Zero가 GitHub에서 PR을 merge했다 (봇이 상태 조회로 감지)."""


Event = (
    ZeroMessage | Command | StageSucceeded | StageFailed | TestsFinished | ReviewFinished | PrMerged
)


@dataclass(frozen=True)
class Limits:
    """한도 (SPEC 3.3). NEEDS_HUMAN에서 /resume하면 초과한 한도만 1회 늘어난다 (Q4)."""

    max_review_rounds: int = 3
    max_test_retries: int = 2


class FixSource(StrEnum):
    TESTS = "tests"  # 테스트 실패
    REVIEW = "review"  # Alpha의 [필수] 지적
    RECOMMENDED = "recommended"  # merge 전 /fix 권장 반영
    RESUME = "resume"  # NEEDS_HUMAN에서 재개: 직전 수정 맥락을 다시 쓴다


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
    """Beta에게 설계를 요청한다. revision이 있으면 Zero의 /revise 요청으로 같은 설계를 고친다."""

    revision: str = ""


@dataclass(frozen=True)
class StartImplement:
    """승인된 설계로 Beta에게 구현을 요청한다."""


@dataclass(frozen=True)
class RunTests:
    """봇이 projects.yaml의 test 명령을 실행한다 (운영 규약 1.7)."""


@dataclass(frozen=True)
class PublishPr:
    """draft PR을 만들거나(첫 회) 본문을 갱신한다 (운영 규약 1.9)."""


@dataclass(frozen=True)
class StartReview:
    """Alpha에게 리뷰를 요청한다."""


@dataclass(frozen=True)
class StartFix:
    source: FixSource


@dataclass(frozen=True)
class ApplyTypeLabel:
    """설계 승인 시 Issue에 type:* 라벨 (운영 규약 4.8)."""


@dataclass(frozen=True)
class MarkReady:
    """APPROVED: PR draft 해제, 남은 [권장] 개수 표시, 멘션."""


@dataclass(frozen=True)
class MarkNeedsHuman:
    """needs-human 라벨, 멘션 (운영 규약 1.8, 2.5)."""

    reason: str


@dataclass(frozen=True)
class ClearNeedsHuman:
    """재개 시 needs-human 라벨을 뗀다."""


@dataclass(frozen=True)
class FinishMerged:
    """merge 감지: Issue 코멘트·종료, worktree 정리 (운영 규약 4.6). 문서 반영은 Phase 3."""


@dataclass(frozen=True)
class CleanupStopped:
    """/stop: Issue를 not planned로 닫고, PR이 없으면 원격 작업 브랜치를 지운다 (1.8, 3.3)."""


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
    INTERRUPTED = "interrupted"
    NEEDS_HUMAN = "needs_human"


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
    | StartImplement
    | RunTests
    | PublishPr
    | StartReview
    | StartFix
    | ApplyTypeLabel
    | MarkReady
    | MarkNeedsHuman
    | ClearNeedsHuman
    | FinishMerged
    | CleanupStopped
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
    def prev_state(self) -> TaskState | None: ...

    @property
    def opinion_rounds(self) -> int: ...

    @property
    def review_round(self) -> int: ...

    @property
    def test_retry(self) -> int: ...

    @property
    def review_limit_bonus(self) -> int: ...

    @property
    def test_limit_bonus(self) -> int: ...

    @property
    def recommended_fixed(self) -> int: ...


# 전이


def start_task(event: PostCreated) -> Transition:
    """게시글 작성 → OPINIONS. 두 에이전트에게 독립된 첫 의견을 요청한다."""
    return Transition(
        TaskState.OPINIONS,
        (RequestOpinions(BOTH_AGENTS, event.text, with_history=False),),
        {"opinion_rounds": 0},
    )


def transition(task: TaskView, event: Event, limits: Limits | None = None) -> Transition:
    limits = limits or Limits()
    state = task.state
    if isinstance(event, Command) and event.name is CommandName.STOP:
        if state.is_terminal:
            return _reject(state, "이미 끝난 작업이다")
        return Transition(
            TaskState.STOPPED,
            (CancelAgentRuns(), CleanupStopped(), PostNotice(NoticeCode.STOPPED)),
        )
    if state is TaskState.OPINIONS:
        return _opinions(task, event)
    if isinstance(event, ZeroMessage):
        return _reject(state)
    handler = _HANDLERS.get(state)
    if handler is not None:
        result = handler(task, event, limits)
        if result is not None:
            return result
    if isinstance(event, Command) and event.name in ALLOWED_COMMANDS[state]:
        raise NotImplementedError(f"{state}의 /{event.name} 전이는 아직 구현하지 않았다")
    if isinstance(event, Command):
        return _reject(state)
    # 상태와 맞지 않는 내부 이벤트 (예: /stop 뒤 늦게 끝난 작업)는 무시한다
    return Transition(state)


def _needs_human(state: TaskState, reason: str, **updates: object) -> Transition:
    return Transition(
        TaskState.NEEDS_HUMAN, (MarkNeedsHuman(reason),), {"prev_state": state, **updates}
    )


def _designing(task: TaskView, event: Event, limits: Limits) -> Transition | None:
    if isinstance(event, StageSucceeded):
        return Transition(TaskState.AWAIT_DESIGN_APPROVAL)
    if isinstance(event, StageFailed):
        return _needs_human(TaskState.DESIGNING, event.reason)
    return None


def _await_design(task: TaskView, event: Event, limits: Limits) -> Transition | None:
    if not isinstance(event, Command):
        return None
    if event.name is CommandName.APPROVE:
        return Transition(TaskState.IMPLEMENTING, (ApplyTypeLabel(), StartImplement()))
    if event.name is CommandName.REVISE:
        request = event.arg.strip()
        if not request:
            return _reject(task.state, "/revise 뒤에 고칠 내용을 적어야 한다")
        return Transition(TaskState.DESIGNING, (StartDesign(request),))
    return None


def _working(task: TaskView, event: Event, limits: Limits) -> Transition | None:
    """IMPLEMENTING, FIXING: 커밋과 push가 끝나면 테스트."""
    if isinstance(event, StageSucceeded):
        return Transition(TaskState.TESTING, (RunTests(),))
    if isinstance(event, StageFailed):
        return _needs_human(task.state, event.reason)
    return None


def _testing(task: TaskView, event: Event, limits: Limits) -> Transition | None:
    if isinstance(event, TestsFinished):
        if event.passed:
            return Transition(TaskState.REVIEWING, (PublishPr(), StartReview()))
        if event.environment_error:
            # 코드로 고칠 수 없으므로 수정을 부르지 않고 재시도 횟수도 세지 않는다.
            # 환경을 고친 뒤 /resume하면 테스트만 다시 돈다
            return _needs_human(TaskState.TESTING, f"테스트 환경 오류: {event.detail}".strip())
        retry = task.test_retry + 1
        if retry > limits.max_test_retries + task.test_limit_bonus:
            return _needs_human(TaskState.TESTING, f"테스트 실패가 {retry}회째다", test_retry=retry)
        # 테스트 실패는 Alpha를 부르지 않고 바로 수정 (운영 규약 1.7)
        return Transition(TaskState.FIXING, (StartFix(FixSource.TESTS),), {"test_retry": retry})
    if isinstance(event, StageFailed):
        return _needs_human(TaskState.TESTING, event.reason)
    return None


def _reviewing(task: TaskView, event: Event, limits: Limits) -> Transition | None:
    if isinstance(event, ReviewFinished):
        if event.approved:
            return Transition(TaskState.AWAIT_MERGE, (MarkReady(),))
        round_ = task.review_round + 1
        if round_ > limits.max_review_rounds + task.review_limit_bonus:
            return _needs_human(
                TaskState.REVIEWING, f"리뷰가 {round_}라운드째다", review_round=round_
            )
        return Transition(TaskState.FIXING, (StartFix(FixSource.REVIEW),), {"review_round": round_})
    if isinstance(event, StageFailed):
        return _needs_human(TaskState.REVIEWING, event.reason)
    return None


def _await_merge(task: TaskView, event: Event, limits: Limits) -> Transition | None:
    if isinstance(event, PrMerged):
        return Transition(TaskState.DONE, (FinishMerged(),))
    if isinstance(event, Command) and event.name is CommandName.FIX:
        if task.recommended_fixed:
            return _reject(task.state, "[권장] 반영은 1회만 할 수 있고 이미 했다")
        return Transition(
            TaskState.FIXING, (StartFix(FixSource.RECOMMENDED),), {"recommended_fixed": 1}
        )
    return None


def _needs_human_state(task: TaskView, event: Event, limits: Limits) -> Transition | None:
    if not (isinstance(event, Command) and event.name is CommandName.RESUME):
        return None
    prev = task.prev_state
    clear: tuple[Effect, ...] = (ClearNeedsHuman(),)
    if prev is TaskState.TESTING:
        if task.test_retry > limits.max_test_retries + task.test_limit_bonus:
            # 초과한 한도만 1회 늘린다. 카운터는 그대로 (Q4)
            return Transition(
                TaskState.FIXING,
                (*clear, StartFix(FixSource.TESTS)),
                {"test_limit_bonus": task.test_limit_bonus + 1},
            )
        return Transition(TaskState.TESTING, (*clear, RunTests()))
    if prev is TaskState.REVIEWING:
        if task.review_round > limits.max_review_rounds + task.review_limit_bonus:
            return Transition(
                TaskState.FIXING,
                (*clear, StartFix(FixSource.REVIEW)),
                {"review_limit_bonus": task.review_limit_bonus + 1},
            )
        return Transition(TaskState.REVIEWING, (*clear, StartReview()))
    if prev is TaskState.DESIGNING:
        return Transition(TaskState.DESIGNING, (*clear, StartDesign()))
    if prev is TaskState.IMPLEMENTING:
        return Transition(TaskState.IMPLEMENTING, (*clear, StartImplement()))
    if prev is TaskState.FIXING:
        return Transition(TaskState.FIXING, (*clear, StartFix(FixSource.RESUME)))
    return _reject(task.state, f"직전 상태({prev})에서는 재개할 수 없다")


_HANDLERS = {
    TaskState.DESIGNING: _designing,
    TaskState.AWAIT_DESIGN_APPROVAL: _await_design,
    TaskState.IMPLEMENTING: _working,
    TaskState.FIXING: _working,
    TaskState.TESTING: _testing,
    TaskState.REVIEWING: _reviewing,
    TaskState.AWAIT_MERGE: _await_merge,
    TaskState.NEEDS_HUMAN: _needs_human_state,
}


def _opinions(task: TaskView, event: Event) -> Transition:
    state = TaskState.OPINIONS
    if not isinstance(event, ZeroMessage | Command):
        return Transition(state)  # 의견 단계에는 내부 이벤트가 없다
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
            (CreateIssue(decision), WriteVaultDecision(decision), StartDesign()),
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
