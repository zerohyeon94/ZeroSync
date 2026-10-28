"""워크플로 엔진 (SPEC 3.4).

Discord 계층이 넘긴 입력(게시글, 메시지, 명령)으로 전이를 계산해 저장하고, 효과를 실행한다.
- 전이와 이벤트 기록은 한 트랜잭션으로 저장한다 (Repository.apply_transition)
- 에이전트·테스트 작업은 작업마다 하나씩 차례로 실행한다. 시작 직전에 상태를 다시 확인해,
  기다리는 사이 /stop 등으로 단계가 바뀌었으면 실행하지 않는다
- /stop은 기다리지 않고 바로 실행 중인 CLI와 테스트를 끈다
- 단계 작업이 끝나면 결과를 내부 이벤트(StageSucceeded, TestsFinished 등)로 넣어 다음 상태로 간다

이 파일은 입력·전이·효과 배분과 의견 단계를 맡고, 설계부터 merge까지의 단계 작업은
`bot.workflow.work.WorkStages`에 있다. 볼트 쓰기와 문서 반영은 Phase 3이다.
"""

import asyncio
import logging
import re
import unicodedata
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from bot.agents.base import (
    AgentName,
    AgentRequest,
    AgentResult,
    AgentRunner,
    EngineName,
    Mode,
    RunStatus,
    Stage,
)
from bot.clock import Clock, SystemClock, from_iso, to_iso
from bot.org import DEFAULT_ORG, Org
from bot.prompts import (
    HistoryEntry,
    Persona,
    debate_prompt,
    opinion_prompt,
    persona_for,
    with_format_error,
)
from bot.render import render_format_error, render_notice, render_opinion, render_opinion_post
from bot.render.hiring import rejected_line, render_hiring_proposal
from bot.schemas import AgentOutputError, Opinion, parse_agent_output
from bot.store import (
    INVALID_OUTPUT,
    Actor,
    EventKind,
    EventRecord,
    HiringStatus,
    NewEvent,
    NotFoundError,
    Repository,
)
from bot.store.repo import StaleStateError, TaskRecord
from bot.workflow.chat import Attachment, Author, ChatIO
from bot.workflow.gate import AgentGate, Priority
from bot.workflow.mentions import Moment, should_mention
from bot.workflow.state import (
    ApplyTypeLabel,
    CancelAgentRuns,
    CleanupStopped,
    ClearNeedsHuman,
    Command,
    CommandName,
    CreateIssue,
    Effect,
    Event,
    FinishMerged,
    Limits,
    MarkNeedsHuman,
    MarkReady,
    NoticeCode,
    PostCreated,
    PostNotice,
    PublishPr,
    RequestDebate,
    RequestOpinions,
    Roster,
    RunTests,
    StageFailed,
    StartDesign,
    StartFix,
    StartImplement,
    StartReview,
    TaskState,
    WriteVaultDecision,
    ZeroMessage,
    start_task,
    transition,
)
from bot.workflow.work import WorkStages

log = logging.getLogger(__name__)

M = TypeVar("M", bound=BaseModel)

# Zero의 말에 바로 답하는 단계. 대기열에서 먼저 꺼낸다 (ADR-007)
_ZERO_FACING = frozenset({Stage.OPINION, Stage.DEBATE})
# 구독 사용량 한도 오류로 보는 문구 [검증 필요] (SPEC V15)
_USAGE_LIMIT = re.compile(
    r"usage limit|rate limit|limit reached|too many requests|quota exceeded|\b429\b", re.I
)
PAUSE_KEY = "queue_paused_until"


def is_usage_limited(result: AgentResult) -> bool:
    """CLI가 구독 사용량 한도로 실패했는지. 성공한 실행은 보지 않는다."""
    if result.status is RunStatus.OK:
        return False
    return bool(_USAGE_LIMIT.search(f"{result.stdout}\n{result.stderr}"))


Outcome = tuple[Event, NewEvent]
Verify = Callable[[Any], Awaitable[list[str]]]

_HISTORY_KINDS = {EventKind.MESSAGE, EventKind.OPINION, EventKind.DEBATE, EventKind.DECISION}
# 재시작 시 NEEDS_HUMAN으로 보내는 진행 중 단계 (Q8). OPINIONS는 안내만 한다
RUNNING_STATES = {
    TaskState.DESIGNING,
    TaskState.IMPLEMENTING,
    TaskState.TESTING,
    TaskState.REVIEWING,
    TaskState.FIXING,
}


@dataclass(frozen=True)
class ProjectContext:
    """프로젝트 하나의 실행 정보. github·feature_dir가 없으면 그 기능을 쓰는 단계는 실패한다."""

    repo: Path
    base_branch: str = "develop"
    test_command: tuple[str, ...] = ()
    github: Any = None  # GitHubClient 또는 테스트용 FakeGitHub
    feature_dir: Path | None = None  # 볼트 `기능/` 폴더. 읽기만 한다 (설계 대상 기능 검증)

    def feature_names(self) -> set[str] | None:
        if self.feature_dir is None or not self.feature_dir.is_dir():
            return None
        # macOS·iCloud 파일 이름은 한글이 분해형(NFD)으로 저장될 수 있다. 조합형(NFC)으로 맞춘다
        return {unicodedata.normalize("NFC", path.stem) for path in self.feature_dir.glob("*.md")}


@dataclass(frozen=True)
class _Answer(Generic[M]):
    """에이전트 한 번의 응답 결과. result가 없으면 형식 오류이거나 실행 실패다."""

    agent: AgentName
    result: M | None
    raw: str = ""
    error: str = ""
    status: RunStatus = RunStatus.OK
    log_path: str = ""
    session_id: str | None = None
    blocked: str = ""  # 실행하지 않은 이유 (하루 예산 초과 등)

    @property
    def failed_to_run(self) -> bool:
        return self.status is not RunStatus.OK or bool(self.blocked)

    @property
    def failure(self) -> str:
        return self.blocked or str(self.status)

    @property
    def opinion(self) -> Any:
        return self.result


@dataclass(frozen=True)
class _Outgoing:
    author: Author
    text: str
    attachments: tuple[Attachment, ...]
    event: NewEvent
    ops_alert: str = ""  # 비어 있지 않으면 #zerosync-ops에도 알린다


@dataclass
class _Running:
    tests: dict[int, str] = field(default_factory=dict)  # 작업 → 실행 중인 테스트 run_id


class Engine(WorkStages):
    def __init__(
        self,
        repo: Repository,
        chat: ChatIO,
        runners: Mapping[EngineName, AgentRunner],
        projects: Mapping[str, ProjectContext],
        *,
        timeout_sec: float,
        org: Org = DEFAULT_ORG,
        git: Any = None,
        tests: Any = None,
        limits: Limits | None = None,
        worktrees_dir: Path | None = None,
        thread_url: Callable[[str], str | None] | None = None,
        clock: Clock | None = None,
        gate: AgentGate | None = None,
        usage_pause: timedelta = timedelta(hours=1),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._repo = repo
        self._chat = chat
        self._runners = runners
        self._org = org
        self._roster = Roster(opinions=org.roles.opinions, callable=org.agent_names)
        self._projects = projects
        self._timeout = timeout_sec
        self._git = git
        self._tests = tests
        self._limits = limits or Limits()
        self._worktrees = worktrees_dir or Path.home() / ".zerosync" / "worktrees"
        self._thread_url = thread_url or (lambda thread: None)
        self._task_locks: dict[int, asyncio.Lock] = {}
        self._running = _Running()
        self._clock = clock or SystemClock()
        self._gate = gate or AgentGate()
        self._usage_pause = usage_pause
        self._sleep = sleep

    @property
    def waiting(self) -> int:
        """대기열에서 차례를 기다리는 에이전트 실행 수."""
        return self._gate.waiting

    # 입력

    async def on_post(
        self, *, project: str, thread: str, title: str, text: str
    ) -> TaskRecord | None:
        """포럼 게시글 → 작업 생성 → 첫 의견. 이미 있는 게시글이면 무시한다."""
        if project not in self._projects:
            raise ValueError(f"알 수 없는 프로젝트: {project}")
        if await self._repo.find_task_by_thread(thread) is not None:
            return None
        result = start_task(PostCreated(title, text), self._roster)
        task = await self._repo.create_task(
            project=project,
            discord_thread=thread,
            title=title,
            state=result.state,
            event=NewEvent(Actor.ZERO, EventKind.MESSAGE, {"title": title, "text": text}),
            updates=result.updates,
        )
        await self._run_effects(task, result.effects)
        return await self._repo.get_task(task.id)

    async def on_message(self, thread: str, text: str, *, message_id: str | None = None) -> None:
        event = NewEvent(Actor.ZERO, EventKind.MESSAGE, {"text": text}, message_id)
        await self._handle(thread, ZeroMessage(text), event)

    async def on_command(
        self, thread: str, name: CommandName, arg: str = "", *, message_id: str | None = None
    ) -> None:
        if name is CommandName.DECIDE and arg.strip():
            event = NewEvent(Actor.ZERO, EventKind.DECISION, {"text": arg.strip()}, message_id)
        else:
            payload = {"name": name.value, "arg": arg}
            event = NewEvent(Actor.ZERO, EventKind.COMMAND, payload, message_id)
        await self._handle(thread, Command(name, arg), event)

    async def _handle(self, thread: str, event: Event, record: NewEvent) -> None:
        task = await self._repo.find_task_by_thread(thread)
        if task is None:
            return
        await self._advance(task.id, event, record)

    async def _advance(self, task_id: int, event: Event, record: NewEvent) -> None:
        """현재 상태로 전이를 계산해 저장하고 효과를 실행한다."""
        task = await self._repo.get_task(task_id)
        try:
            result = transition(task, event, self._limits, self._roster)
        except NotImplementedError:
            await self._repo.add_event(task.id, record)
            await self._notice(task, NoticeCode.NOT_IMPLEMENTED, f"현재 상태: {task.state}")
            return
        try:
            task = await self._repo.apply_transition(
                task.id,
                expected_state=task.state,
                new_state=result.state,
                event=record,
                updates=result.updates,
            )
        except StaleStateError:
            # 그 사이 다른 입력이 상태를 바꿨다. 바뀐 상태 기준으로 다시 판단한다
            await self._advance(task_id, event, record)
            return
        await self._run_effects(task, result.effects)

    async def recover_interrupted(self) -> None:
        """재시작 전에 끝나지 않은 작업을 정리한다 (SPEC 3.4, Q8).

        중간 결과는 신뢰하지 않는다. 남은 에이전트 실행은 error로 닫는다.
        OPINIONS는 실패 안내 후 그대로 두고(다시 질문하면 재요청), 진행 중 단계(설계·구현·
        테스트·리뷰·수정)는 NEEDS_HUMAN으로 보낸다 (2026-10-10 Zero 결정).
        """
        by_task: dict[int, list[str]] = {}
        for run in await self._repo.list_running_agent_runs():
            await self._repo.finish_agent_run(
                run.id, status=RunStatus.ERROR, exit_code=None, log_path=run.log_path
            )
            by_task.setdefault(run.task_id, []).append(run.agent)

        for task in await self._repo.list_tasks(RUNNING_STATES | {TaskState.OPINIONS}):
            agents = by_task.get(task.id, [])
            if task.state is TaskState.OPINIONS:
                if not agents:
                    continue
                names = ", ".join(self._org.display(agent) for agent in sorted(set(agents)))
                await self._repo.add_event(
                    task.id,
                    NewEvent(Actor.BOT, EventKind.ERROR, {"reason": "restart", "agents": agents}),
                )
                await self._chat.post(
                    task.discord_thread,
                    "bot",
                    render_notice(NoticeCode.AGENT_FAILED, f"[{names}] 봇 재시작으로 중단"),
                    mention=should_mention(Moment.OPINIONS_READY),
                )
            else:
                await self._repo.apply_transition(
                    task.id,
                    expected_state=task.state,
                    new_state=TaskState.NEEDS_HUMAN,
                    event=NewEvent(Actor.BOT, EventKind.ERROR, {"reason": "restart"}),
                    updates={"prev_state": task.state},
                )
                await self._chat.post(
                    task.discord_thread,
                    "bot",
                    render_notice(NoticeCode.INTERRUPTED),
                    mention=should_mention(Moment.NEEDS_HUMAN),
                )
                await self._label_needs_human(task, add=True)
            await self._chat.notify_ops(
                f"[{task.project}] 작업 {task.id}: 봇 재시작으로 중단했다 "
                f"(상태 {task.state}, 중단한 실행 {len(agents)}건)",
                mention=should_mention(Moment.BOT_ERROR),
            )

    async def remind_waiting(self, after: timedelta) -> int:
        """Zero 대기가 after를 넘은 작업에 1회만 다시 멘션한다 (운영 규약 2.5). 보낸 수."""
        now = self._clock.now()
        sent = 0
        waiting = {state for state in TaskState if state.waits_for_zero}
        for task in await self._repo.list_tasks(waiting):
            if task.waiting_since is None or task.reminded_at is not None:
                continue
            if now - from_iso(task.waiting_since) < after:
                continue
            hours = int((now - from_iso(task.waiting_since)).total_seconds() // 3600)
            await self._chat.post(
                task.discord_thread,
                "bot",
                render_notice(NoticeCode.REMINDER, f"현재 상태: {task.state} ({hours}시간째)"),
                mention=should_mention(Moment.REMINDER),
            )
            await self._repo.update_fields(task.id, {"reminded_at": to_iso(now)})
            sent += 1
        return sent

    # 효과

    async def _run_effects(self, task: TaskRecord, effects: Sequence[Effect]) -> None:
        for effect in effects:
            if isinstance(effect, CancelAgentRuns):
                await self._cancel_runs(task.id)
            elif isinstance(effect, PostNotice):
                await self._notice(task, effect.code, effect.detail)
            elif isinstance(effect, RequestOpinions):
                await self._serialized(
                    task.id, TaskState.OPINIONS, lambda e=effect: self._opinions(task, e)
                )
            elif isinstance(effect, RequestDebate):
                await self._serialized(task.id, TaskState.OPINIONS, lambda: self._debate(task))
            elif isinstance(effect, CreateIssue):
                await self._stage(task.id, TaskState.DESIGNING, lambda: self._create_issue(task.id))
            elif isinstance(effect, WriteVaultDecision):
                pass  # 볼트 결정 노트는 Phase 3. Issue 생성 안내에 함께 알린다
            elif isinstance(effect, StartDesign):
                await self._stage(
                    task.id, TaskState.DESIGNING, lambda e=effect: self._design(task.id, e.revision)
                )
            elif isinstance(effect, StartImplement):
                await self._stage(task.id, TaskState.IMPLEMENTING, lambda: self._implement(task.id))
            elif isinstance(effect, RunTests):
                await self._stage(task.id, TaskState.TESTING, lambda: self._run_tests(task.id))
            elif isinstance(effect, PublishPr):
                await self._stage(task.id, TaskState.REVIEWING, lambda: self._publish_pr(task.id))
            elif isinstance(effect, StartReview):
                await self._stage(task.id, TaskState.REVIEWING, lambda: self._review(task.id))
            elif isinstance(effect, StartFix):
                await self._stage(
                    task.id, TaskState.FIXING, lambda e=effect: self._fix(task.id, e.source)
                )
            elif isinstance(effect, ApplyTypeLabel):
                await self._side_effect(task.id, self._apply_type_label)
            elif isinstance(effect, MarkReady):
                await self._side_effect(task.id, self._mark_ready)
            elif isinstance(effect, MarkNeedsHuman):
                await self._mark_needs_human(task.id, effect.reason)
            elif isinstance(effect, ClearNeedsHuman):
                await self._side_effect(task.id, lambda t: self._label_needs_human(t, add=False))
            elif isinstance(effect, FinishMerged):
                await self._side_effect(task.id, self._finish_merged)
            elif isinstance(effect, CleanupStopped):
                await self._side_effect(task.id, self._cleanup_stopped)
            else:  # pragma: no cover - 새 효과 타입을 추가하면 여기서 드러난다
                raise TypeError(f"처리하지 않은 효과: {effect!r}")

    async def _serialized(
        self, task_id: int, expected: TaskState, work: Callable[[], Awaitable[Any]]
    ) -> Any:
        """작업마다 하나씩 실행한다. 시작 직전 상태가 expected가 아니면 실행하지 않는다."""
        lock = self._task_locks.setdefault(task_id, asyncio.Lock())
        async with lock:
            current = await self._repo.get_task(task_id)
            if current.state is not expected:
                return None
            return await work()

    async def _stage(
        self, task_id: int, expected: TaskState, work: Callable[[], Awaitable[Outcome | None]]
    ) -> None:
        """단계 작업을 실행하고 결과 이벤트로 다음 상태로 간다. 예외는 단계 실패로 바꾼다."""

        async def guarded() -> Outcome | None:
            try:
                return await work()
            except Exception as error:
                log.exception("작업 %s 단계 실패", task_id)
                reason = f"{type(error).__name__}: {error}"
                task = await self._repo.get_task(task_id)
                await self._chat.notify_ops(
                    f"[{task.project}] 작업 {task.id} {task.state} 중 오류: {reason}",
                    mention=should_mention(Moment.BOT_ERROR),
                )
                return StageFailed(reason), NewEvent(
                    Actor.BOT, EventKind.ERROR, {"state": task.state.value, "reason": reason}
                )

        outcome = await self._serialized(task_id, expected, guarded)
        if outcome is not None:
            await self._advance(task_id, *outcome)

    async def _side_effect(
        self, task_id: int, work: Callable[[TaskRecord], Awaitable[None]]
    ) -> None:
        """GitHub 라벨·정리처럼 실패해도 상태를 바꾸지 않는 작업. 실패는 운영 채널에 알린다."""
        task = await self._repo.get_task(task_id)
        try:
            await work(task)
        except Exception as error:
            log.exception("작업 %s 부수 작업 실패", task_id)
            await self._chat.notify_ops(
                f"[{task.project}] 작업 {task.id} 처리 중 오류: {type(error).__name__}: {error}",
                mention=should_mention(Moment.BOT_ERROR),
            )

    async def _cancel_runs(self, task_id: int) -> None:
        for run in await self._repo.list_running_agent_runs(task_id):
            await self._runner(run.agent).cancel(run.id)
        test_run = self._running.tests.get(task_id)
        if test_run is not None and self._tests is not None:
            await self._tests.cancel(test_run)

    async def _notice(self, task: TaskRecord, code: NoticeCode, detail: str = "") -> None:
        await self._chat.post(
            task.discord_thread,
            "bot",
            render_notice(code, detail),
            mention=should_mention(Moment.NOTICE),
        )

    async def _say(self, task: TaskRecord, text: str, moment: Moment = Moment.NOTICE) -> str:
        return await self._chat.post(
            task.discord_thread, "bot", text, mention=should_mention(moment)
        )

    # 에이전트 호출

    def _runner(self, agent: AgentName) -> AgentRunner:
        return self._runners[self._org.engine(agent)]

    def _name(self, agent: str) -> str:
        return self._org.display(agent)

    async def _persona(self, agent: AgentName) -> Persona:
        """인격과 이 팀장이 거절당한 채용 제안 (같은 제안 반복 방지, 운영 규약 1.12)."""
        rejected = await self._repo.list_hiring_proposals(
            proposed_by=agent, status=HiringStatus.REJECTED
        )
        lines = [rejected_line(r.payload, r.decided_note) for r in rejected]
        return persona_for(self._org, agent, lines)

    async def _ask(
        self,
        task: TaskRecord,
        agent: AgentName,
        stage: Stage,
        prompt: str,
        *,
        model: type[M] = Opinion,  # type: ignore[assignment]
        mode: Mode = "read_only",
        cwd: Path | None = None,
        context: dict[str, Any] | None = None,
        resume: str | None = None,
        verify: Verify | None = None,
    ) -> _Answer[M]:
        """에이전트를 부르고 스키마로 검증한다.

        형식 오류이거나 verify가 문제를 찾으면 그 내용을 붙여 1회 재요청한다 (운영 규약 2.1).
        """
        call = dict(model=model, mode=mode, cwd=cwd, context=context, verify=verify)
        answer = await self._attempt(task, agent, stage, prompt, resume=resume, **call)
        if answer.result is None and not answer.failed_to_run:
            retry = with_format_error(prompt, answer.error)
            answer = await self._attempt(
                task, agent, stage, retry, resume=answer.session_id or resume, **call
            )
        proposal = getattr(answer.result, "hiring_proposal", None)
        if proposal is not None:
            await self._record_hiring(task, agent, proposal)
        return answer

    # 채용 제안 (운영 규약 1.12, SPEC Q19)

    async def _record_hiring(self, task: TaskRecord, agent: AgentName, proposal: Any) -> None:
        """제안을 저장하고 숫자 근거를 붙여 Zero에게 올린다. 실패해도 단계는 계속한다."""
        try:
            evidence = {
                "runs": await self._repo.count_agent_runs(agent),
                "errors": await self._repo.count_errors(),
            }
            record = await self._repo.add_hiring_proposal(
                task_id=task.id,
                proposed_by=agent,
                payload=proposal.model_dump(mode="json"),
                evidence=evidence,
            )
            await self._chat.notify_ops(
                render_hiring_proposal(record.id, self._name(agent), proposal, evidence),
                mention=should_mention(Moment.HIRING_PROPOSAL),
            )
        except Exception:
            log.exception("채용 제안 기록 실패 (작업 %s, %s)", task.id, agent)

    async def decide_hiring(self, proposal_id: int, *, accept: bool, note: str = "") -> str:
        """Zero의 /hire 답. 수락은 기록만 하고 org.yaml 변경은 Zero가 한다."""
        try:
            record = await self._repo.decide_hiring_proposal(
                proposal_id, accept=accept, note=note.strip()
            )
        except NotFoundError:
            return f"채용 제안 #{proposal_id}이 없다."
        except StaleStateError as error:
            return str(error)
        name = self._name(record.proposed_by)
        if accept:
            return (
                f"채용 제안 #{proposal_id}({name})을 수락으로 기록했다. "
                "org.yaml과 인격 파일을 추가하고 봇을 다시 시작하면 반영된다."
            )
        return (
            f"채용 제안 #{proposal_id}({name})을 거절로 기록했다. "
            "다음부터 이 팀장의 프롬프트에 거절 이유가 들어간다."
        )

    async def _attempt(
        self,
        task: TaskRecord,
        agent: AgentName,
        stage: Stage,
        prompt: str,
        **call: Any,
    ) -> _Answer[Any]:
        """대기열에서 차례를 받아 한 번 실행한다 (ADR-007: 한 번에 하나, 하루 예산, 한도 정지)."""
        priority: Priority = (
            0 if stage in _ZERO_FACING else 1,
            self._project_rank(task.project),
            task.id,
        )
        async with self._gate.slot(priority):
            current = await self._repo.get_task(task.id)
            if current.state.is_terminal:
                # 기다리는 사이 /stop됐다. 호출하지 않는다
                return _Answer(agent, None, status=RunStatus.CANCELLED)
            await self._wait_if_paused()
            blocked = await self._over_budget(agent)
            if blocked:
                await self._chat.notify_ops(
                    f"[{task.project}] 작업 {task.id}: {blocked}",
                    mention=should_mention(Moment.NEEDS_HUMAN),
                )
                return _Answer(agent, None, status=RunStatus.ERROR, blocked=blocked)
            answer, limited = await self._run_once(task, agent, stage, prompt, **call)
            if limited:
                # 한도가 풀리면 같은 요청을 한 번 다시 실행한다
                await self._pause_for_usage(task, agent)
                await self._wait_if_paused()
                answer, _ = await self._run_once(task, agent, stage, prompt, **call)
            return answer

    def _project_rank(self, project: str) -> int:
        # 제품 순서 = 설정의 프로젝트 순서 (가게씨 → 제이데이 → 오롯, ADR-007)
        keys = list(self._projects)
        return keys.index(project) if project in keys else len(keys)

    def _day_start(self) -> str:
        """이 맥 시간대의 오늘 0시 (UTC ISO). 하루 예산의 기준이다."""
        local = self._clock.now().astimezone()
        return to_iso(local.replace(hour=0, minute=0, second=0, microsecond=0))

    async def _over_budget(self, agent: AgentName) -> str:
        spec = self._org.agents.get(agent)
        limit = spec.daily_calls if spec is not None else None
        if limit is None:
            return ""
        used = await self._repo.count_agent_runs_since(agent, self._day_start())
        if used < limit:
            return ""
        return f"{self._name(agent)}의 오늘 호출 한도 {limit}회를 넘었다"

    async def _paused_until(self) -> datetime | None:
        value = await self._repo.get_state(PAUSE_KEY)
        return from_iso(value) if value else None

    async def _wait_if_paused(self) -> None:
        while True:
            until = await self._paused_until()
            if until is None:
                return
            remaining = (until - self._clock.now()).total_seconds()
            if remaining <= 0:
                await self._repo.set_state(PAUSE_KEY, None)
                await self._chat.notify_ops(
                    "사용량 한도 정지가 끝나 대기열을 다시 시작한다.",
                    mention=should_mention(Moment.NOTICE),
                )
                return
            await self._sleep(min(remaining, 60.0))

    async def _pause_for_usage(self, task: TaskRecord, agent: AgentName) -> None:
        until = self._clock.now() + self._usage_pause
        await self._repo.set_state(PAUSE_KEY, to_iso(until))
        local = until.astimezone().strftime("%m-%d %H:%M")
        await self._chat.notify_ops(
            f"[{task.project}] 작업 {task.id}: {self._name(agent)} 실행이 구독 사용량 한도에 "
            f"걸렸다. 대기열을 {local}까지 멈추고 그 뒤 다시 실행한다.",
            mention=should_mention(Moment.BOT_ERROR),
        )

    async def _run_once(
        self,
        task: TaskRecord,
        agent: AgentName,
        stage: Stage,
        prompt: str,
        *,
        model: type[M],
        mode: Mode,
        cwd: Path | None,
        context: dict[str, Any] | None,
        resume: str | None,
        verify: Verify | None,
    ) -> tuple[_Answer[M], bool]:
        """CLI를 한 번 실행하고 검증한다. 두 번째 값은 사용량 한도로 실패했는지."""
        run_id = f"t{task.id}-{agent}-{stage.value}-{uuid.uuid4().hex[:8]}"
        await self._repo.start_agent_run(
            run_id, task_id=task.id, agent=agent, stage=stage, engine=self._org.engine(agent)
        )
        request = AgentRequest(
            run_id=run_id,
            task_id=task.id,
            stage=stage,
            prompt=prompt,
            cwd=cwd or self._projects[task.project].repo,
            mode=mode,
            timeout_sec=self._timeout,
            resume_session=resume if self._org.engine(agent) == "claude" else None,
            output_schema=model.model_json_schema(),
            model=self._org.model(agent, stage),
        )
        try:
            result = await self._runner(agent).run(request)
        except BaseException:
            await self._repo.finish_agent_run(
                run_id, status=RunStatus.ERROR, exit_code=None, log_path=None
            )
            raise

        log_path = str(result.log_path)
        status: RunStatus | str = result.status
        parsed, error = None, ""
        if result.status is RunStatus.OK:
            try:
                parsed = parse_agent_output(result.stdout, model, context)
                problems = await verify(parsed) if verify is not None else []
                if problems:
                    parsed = None
                    error = "출력은 형식에 맞지만 작업 결과에 문제가 있다:\n" + "\n".join(
                        f"- {problem}" for problem in problems
                    )
                    status = INVALID_OUTPUT
            except AgentOutputError as e:
                status, error = INVALID_OUTPUT, str(e)
        await self._repo.finish_agent_run(
            run_id, status=status, exit_code=result.exit_code, log_path=log_path
        )
        answer = _Answer(
            agent, parsed, result.stdout, error, result.status, log_path, result.session_id
        )
        return answer, is_usage_limited(result)

    # 의견

    async def _opinions(self, task: TaskRecord, effect: RequestOpinions) -> None:
        post = await self._post_text(task)
        history = await self._history(task) if effect.with_history else []
        prompts = {
            agent: opinion_prompt(
                await self._persona(agent),
                title=task.title,
                post=post,
                question=effect.question,
                history=history,
            )
            for agent in effect.agents
        }
        answers = await asyncio.gather(
            *(self._ask(task, agent, Stage.OPINION, prompts[agent]) for agent in effect.agents)
        )
        payload = {"question": effect.question} if effect.with_history else {"first": True}
        await self._publish(task, answers, EventKind.OPINION, payload, heading="")

    async def _debate(self, task: TaskRecord) -> None:
        latest = await self._latest_opinions(task.id)
        pair = self._org.roles.opinions[:2]
        missing = [agent for agent in pair if agent not in latest]
        if len(pair) < 2 or missing:
            names = ", ".join(self._name(agent) for agent in missing)
            detail = f"/debate는 두 의견이 모두 있어야 한다. 의견이 없는 쪽: {names}"
            await self._notice(task, NoticeCode.REJECTED, detail)
            return
        post = await self._post_text(task)
        history = await self._history(task)
        first, second = pair
        prompts = {
            agent: debate_prompt(
                await self._persona(agent),
                title=task.title,
                post=post,
                own=render_opinion(latest[agent]),
                other_name=self._name(other),
                other=render_opinion(latest[other]),
                history=history,
            )
            for agent, other in ((first, second), (second, first))
        }
        answers = await asyncio.gather(
            *(self._ask(task, agent, Stage.DEBATE, prompts[agent]) for agent in pair)
        )
        await self._publish(task, answers, EventKind.DEBATE, {}, heading="반박")

    async def _publish(
        self,
        task: TaskRecord,
        answers: Sequence[_Answer[Opinion]],
        kind: EventKind,
        payload: Mapping[str, object],
        *,
        heading: str,
    ) -> None:
        """응답을 의견 담당 순서(roles.opinions)로 게시하고 기록한다. 마지막 게시에서 멘션한다."""
        current = await self._repo.get_task(task.id)
        if current.state is not TaskState.OPINIONS:
            return  # 실행 중 /stop 등으로 단계가 바뀌었다. 결과를 게시하지 않는다

        order = list(self._org.roles.opinions) + list(self._org.agent_names)
        ordered = sorted(answers, key=lambda answer: order.index(answer.agent))
        outgoing = [self._outgoing(task, answer, kind, payload, heading) for answer in ordered]
        mention = should_mention(Moment.OPINIONS_READY)
        for index, item in enumerate(outgoing):
            message_id = await self._chat.post(
                task.discord_thread,
                item.author,
                item.text,
                mention=mention and index == len(outgoing) - 1,
                attachments=item.attachments,
            )
            event = item.event
            await self._repo.add_event(
                task.id, NewEvent(event.actor, event.kind, event.payload, message_id)
            )
            if item.ops_alert:
                await self._chat.notify_ops(
                    item.ops_alert, mention=should_mention(Moment.BOT_ERROR)
                )

    def _outgoing(
        self,
        task: TaskRecord,
        answer: _Answer[Opinion],
        kind: EventKind,
        payload: Mapping[str, object],
        heading: str,
    ) -> _Outgoing:
        actor = answer.agent
        if answer.result is not None:
            rendered = render_opinion_post(answer.result, heading=heading)
            data = {**payload, "opinion": answer.result.model_dump(mode="json")}
            return _Outgoing(
                answer.agent, rendered.text, rendered.attachments, NewEvent(actor, kind, data)
            )
        if not answer.failed_to_run:
            rendered = render_format_error(answer.raw, answer.error)
            data = {**payload, "reason": INVALID_OUTPUT, "error": answer.error, "raw": answer.raw}
            event = NewEvent(actor, EventKind.ERROR, data)
            return _Outgoing(answer.agent, rendered.text, rendered.attachments, event)
        # CLI 실행 실패: [ZeroSync] 안내 + 운영 채널 알림 (운영 규약 2.5)
        name = self._name(answer.agent)
        data = {**payload, "agent": answer.agent, "status": answer.failure}
        alert = (
            f"[{task.project}] 작업 {task.id} {name} {kind.value} 실행 실패: "
            f"{answer.failure}. 로그: {answer.log_path}"
            if answer.status is not RunStatus.CANCELLED and not answer.blocked
            else ""
        )
        return _Outgoing(
            "bot",
            render_notice(NoticeCode.AGENT_FAILED, f"[{name}] {answer.failure}"),
            (),
            NewEvent(Actor.BOT, EventKind.ERROR, data),
            alert,
        )

    # 맥락

    async def _events(self, task_id: int) -> list[EventRecord]:
        return await self._repo.list_events(task_id, _HISTORY_KINDS)

    async def _post_text(self, task: TaskRecord) -> str:
        events = await self._events(task.id)
        first = events[0].payload if events else {}
        return str(first.get("text", "")) if isinstance(first, dict) else ""

    async def _history(self, task: TaskRecord) -> list[HistoryEntry]:
        """게시글 뒤의 흐름 (운영 규약 1.6). 첫 게시글은 프롬프트의 작업 절에 따로 들어간다."""
        entries = []
        for event in (await self._events(task.id))[1:]:
            payload = event.payload if isinstance(event.payload, dict) else {}
            if event.kind in (EventKind.OPINION, EventKind.DEBATE):
                opinion = Opinion.model_validate(payload["opinion"])
                heading = "반박" if event.kind is EventKind.DEBATE else ""
                entries.append(
                    HistoryEntry(self._name(event.actor), render_opinion(opinion, heading=heading))
                )
            elif event.kind is EventKind.DECISION:
                entries.append(HistoryEntry("Zero", f"/decide {payload.get('text', '')}"))
            else:
                entries.append(HistoryEntry(self._name(event.actor), str(payload.get("text", ""))))
        return entries

    async def _latest_opinions(self, task_id: int) -> dict[AgentName, Opinion]:
        latest: dict[AgentName, Opinion] = {}
        for event in await self._repo.list_events(task_id, {EventKind.OPINION, EventKind.DEBATE}):
            if self._org.has(event.actor):
                latest[event.actor] = Opinion.model_validate(event.payload["opinion"])
        return latest
