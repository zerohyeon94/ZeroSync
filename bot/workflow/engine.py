"""워크플로 엔진 (SPEC 3.4).

Discord 계층이 넘긴 입력(게시글, 메시지, 명령)으로 전이를 계산해 저장하고, 효과를 실행한다.
- 전이와 이벤트 기록은 한 트랜잭션으로 저장한다 (Repository.apply_transition)
- 에이전트 호출 효과는 작업마다 하나씩 차례로 실행한다.
  /stop은 기다리지 않고 바로 실행 중인 CLI를 끈다
- 현재 구현 범위: OPINIONS 단계 (의견, 추가 질문, /debate, /decide 기록, /stop)
  /decide 뒤의 Issue·볼트·설계 효과는 Phase 2에서 실행한다. 지금은 결정을 기록하고 안내만 한다
"""

import asyncio
import logging
import uuid
from collections.abc import Coroutine, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bot.agents.base import AgentName, AgentRequest, AgentRunner, RunStatus, Stage
from bot.prompts import (
    DISPLAY_NAMES,
    HistoryEntry,
    debate_prompt,
    opinion_prompt,
    with_format_error,
)
from bot.render import render_format_error, render_notice, render_opinion, render_opinion_post
from bot.schemas import AgentOutputError, Opinion, parse_agent_output
from bot.store import INVALID_OUTPUT, Actor, EventKind, EventRecord, NewEvent, Repository
from bot.store.repo import StaleStateError, TaskRecord
from bot.workflow.chat import Attachment, Author, ChatIO
from bot.workflow.mentions import Moment, should_mention
from bot.workflow.state import (
    BOTH_AGENTS,
    CancelAgentRuns,
    Command,
    CommandName,
    CreateIssue,
    Effect,
    Event,
    NoticeCode,
    PostCreated,
    PostNotice,
    RequestDebate,
    RequestOpinions,
    StartDesign,
    TaskState,
    WriteVaultDecision,
    ZeroMessage,
    start_task,
    transition,
)

log = logging.getLogger(__name__)

# Phase 2에서 실행할 /decide 효과
_DEFERRED_EFFECTS = (CreateIssue, WriteVaultDecision, StartDesign)
_HISTORY_KINDS = {EventKind.MESSAGE, EventKind.OPINION, EventKind.DEBATE, EventKind.DECISION}


@dataclass(frozen=True)
class _Answer:
    """에이전트 한 번의 응답 결과. opinion이 없으면 형식 오류이거나 실행 실패다."""

    agent: AgentName
    opinion: Opinion | None
    raw: str = ""
    error: str = ""
    status: RunStatus = RunStatus.OK
    log_path: str = ""

    @property
    def failed_to_run(self) -> bool:
        return self.status is not RunStatus.OK


@dataclass(frozen=True)
class _Outgoing:
    author: Author
    text: str
    attachments: tuple[Attachment, ...]
    event: NewEvent
    ops_alert: str = ""  # 비어 있지 않으면 #zerosync-ops에도 알린다


class Engine:
    def __init__(
        self,
        repo: Repository,
        chat: ChatIO,
        runners: Mapping[AgentName, AgentRunner],
        repos: Mapping[str, Path],
        *,
        timeout_sec: float,
    ):
        """repos는 프로젝트 키 → 앱 저장소 경로. 의견 단계의 에이전트는 이 폴더에서 읽기만 한다."""
        self._repo = repo
        self._chat = chat
        self._runners = runners
        self._repos = repos
        self._timeout = timeout_sec
        self._task_locks: dict[int, asyncio.Lock] = {}

    # 입력

    async def on_post(
        self, *, project: str, thread: str, title: str, text: str
    ) -> TaskRecord | None:
        """포럼 게시글 → 작업 생성 → 첫 의견. 이미 있는 게시글이면 무시한다."""
        if project not in self._repos:
            raise ValueError(f"알 수 없는 프로젝트: {project}")
        if await self._repo.find_task_by_thread(thread) is not None:
            return None
        result = start_task(PostCreated(title, text))
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
        try:
            result = transition(task, event)
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
            await self._handle(thread, event, record)
            return
        await self._run_effects(task, result.effects)

    # 효과

    async def _run_effects(self, task: TaskRecord, effects: Sequence[Effect]) -> None:
        deferred = False
        for effect in effects:
            if isinstance(effect, CancelAgentRuns):
                await self._cancel_runs(task.id)
            elif isinstance(effect, PostNotice):
                await self._notice(task, effect.code, effect.detail)
            elif isinstance(effect, RequestOpinions):
                await self._serialized(task, self._opinions(task, effect))
            elif isinstance(effect, RequestDebate):
                await self._serialized(task, self._debate(task))
            elif isinstance(effect, _DEFERRED_EFFECTS):
                deferred = True
            else:  # pragma: no cover - 새 효과 타입을 추가하면 여기서 드러난다
                raise TypeError(f"처리하지 않은 효과: {effect!r}")
        if deferred:
            await self._notice(task, NoticeCode.DECISION_RECORDED)

    async def _serialized(self, task: TaskRecord, work: Coroutine[Any, Any, None]) -> None:
        lock = self._task_locks.setdefault(task.id, asyncio.Lock())
        async with lock:
            current = await self._repo.get_task(task.id)
            if current.state is not TaskState.OPINIONS:
                # 기다리는 사이 /stop 또는 /decide로 단계가 바뀌었다
                work.close()
                return
            await work

    async def _cancel_runs(self, task_id: int) -> None:
        for run in await self._repo.list_running_agent_runs(task_id):
            await self._runners[run.agent].cancel(run.id)

    async def _notice(self, task: TaskRecord, code: NoticeCode, detail: str = "") -> None:
        await self._chat.post(
            task.discord_thread,
            "bot",
            render_notice(code, detail),
            mention=should_mention(Moment.NOTICE),
        )

    # 의견

    async def _opinions(self, task: TaskRecord, effect: RequestOpinions) -> None:
        post = await self._post_text(task)
        history = await self._history(task) if effect.with_history else []
        prompts = {
            agent: opinion_prompt(
                agent, title=task.title, post=post, question=effect.question, history=history
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
        missing = [agent for agent in BOTH_AGENTS if agent not in latest]
        if missing:
            names = ", ".join(DISPLAY_NAMES[agent] for agent in missing)
            detail = f"/debate는 두 의견이 모두 있어야 한다. 의견이 없는 쪽: {names}"
            await self._notice(task, NoticeCode.REJECTED, detail)
            return
        post = await self._post_text(task)
        history = await self._history(task)
        prompts = {
            agent: debate_prompt(
                agent,
                title=task.title,
                post=post,
                own=render_opinion(latest[agent]),
                other_agent=other,
                other=render_opinion(latest[other]),
                history=history,
            )
            for agent, other in (("claude", "codex"), ("codex", "claude"))
        }
        answers = await asyncio.gather(
            *(self._ask(task, agent, Stage.DEBATE, prompts[agent]) for agent in BOTH_AGENTS)
        )
        await self._publish(task, answers, EventKind.DEBATE, {}, heading="반박")

    async def _ask(self, task: TaskRecord, agent: AgentName, stage: Stage, prompt: str) -> _Answer:
        """에이전트를 부르고 의견으로 검증한다.

        형식 오류면 오류를 붙여 1회 재요청한다 (운영 규약 2.1).
        """
        answer = await self._attempt(task, agent, stage, prompt)
        if answer.opinion is not None or answer.failed_to_run:
            return answer
        return await self._attempt(task, agent, stage, with_format_error(prompt, answer.error))

    async def _attempt(
        self, task: TaskRecord, agent: AgentName, stage: Stage, prompt: str
    ) -> _Answer:
        run_id = f"t{task.id}-{agent}-{stage.value}-{uuid.uuid4().hex[:8]}"
        await self._repo.start_agent_run(run_id, task_id=task.id, agent=agent, stage=stage)
        request = AgentRequest(
            run_id=run_id,
            task_id=task.id,
            stage=stage,
            prompt=prompt,
            cwd=self._repos[task.project],
            mode="read_only",
            timeout_sec=self._timeout,
            output_schema=Opinion.model_json_schema(),
        )
        try:
            result = await self._runners[agent].run(request)
        except BaseException:
            await self._repo.finish_agent_run(
                run_id, status=RunStatus.ERROR, exit_code=None, log_path=None
            )
            raise

        log_path = str(result.log_path)
        status: RunStatus | str = result.status
        opinion, error = None, ""
        if result.status is RunStatus.OK:
            try:
                opinion = parse_agent_output(result.stdout, Opinion)
            except AgentOutputError as e:
                status, error = INVALID_OUTPUT, str(e)
        await self._repo.finish_agent_run(
            run_id, status=status, exit_code=result.exit_code, log_path=log_path
        )
        return _Answer(agent, opinion, result.stdout, error, result.status, log_path)

    async def _publish(
        self,
        task: TaskRecord,
        answers: Sequence[_Answer],
        kind: EventKind,
        payload: Mapping[str, object],
        *,
        heading: str,
    ) -> None:
        """응답을 Beta, Alpha 순서로 게시하고 기록한다. 마지막 게시에서 Zero를 멘션한다."""
        current = await self._repo.get_task(task.id)
        if current.state is not TaskState.OPINIONS:
            return  # 실행 중 /stop 등으로 단계가 바뀌었다. 결과를 게시하지 않는다

        ordered = sorted(answers, key=lambda answer: BOTH_AGENTS.index(answer.agent))
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
        answer: _Answer,
        kind: EventKind,
        payload: Mapping[str, object],
        heading: str,
    ) -> _Outgoing:
        actor = Actor(answer.agent)
        if answer.opinion is not None:
            rendered = render_opinion_post(answer.opinion, heading=heading)
            data = {**payload, "opinion": answer.opinion.model_dump(mode="json")}
            return _Outgoing(
                answer.agent, rendered.text, rendered.attachments, NewEvent(actor, kind, data)
            )
        if not answer.failed_to_run:
            rendered = render_format_error(answer.raw, answer.error)
            data = {**payload, "reason": INVALID_OUTPUT, "error": answer.error, "raw": answer.raw}
            event = NewEvent(actor, EventKind.ERROR, data)
            return _Outgoing(answer.agent, rendered.text, rendered.attachments, event)
        # CLI 실행 실패: [ZeroSync] 안내 + 운영 채널 알림 (운영 규약 2.5)
        name = DISPLAY_NAMES[answer.agent]
        data = {**payload, "agent": answer.agent, "status": str(answer.status)}
        alert = (
            f"[{task.project}] 작업 {task.id} {name} {kind.value} 실행 실패: "
            f"{answer.status}. 로그: {answer.log_path}"
            if answer.status is not RunStatus.CANCELLED
            else ""
        )
        return _Outgoing(
            "bot",
            render_notice(NoticeCode.AGENT_FAILED, f"[{name}] {answer.status}"),
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
                    HistoryEntry(event.actor.value, render_opinion(opinion, heading=heading))
                )
            elif event.kind is EventKind.DECISION:
                entries.append(HistoryEntry("zero", f"/decide {payload.get('text', '')}"))
            else:
                entries.append(HistoryEntry(event.actor.value, str(payload.get("text", ""))))
        return entries

    async def _latest_opinions(self, task_id: int) -> dict[AgentName, Opinion]:
        latest: dict[AgentName, Opinion] = {}
        for event in await self._repo.list_events(task_id, {EventKind.OPINION, EventKind.DEBATE}):
            if event.actor in (Actor.CLAUDE, Actor.CODEX):
                latest[event.actor.value] = Opinion.model_validate(event.payload["opinion"])
        return latest
