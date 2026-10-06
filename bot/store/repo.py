"""tasks, events, agent_runs 접근 (SPEC 8).

상태 변경은 이벤트 기록과 함께 한 트랜잭션으로 저장한다 (SPEC 3.4).
하나의 연결을 여러 코루틴이 함께 쓰므로 트랜잭션은 락으로 순서를 지킨다.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import aiosqlite

from bot.agents.base import AgentName, RunStatus, Stage
from bot.clock import Clock, to_iso
from bot.workflow.state import TaskState


class Actor(StrEnum):
    ZERO = "zero"
    CLAUDE = "claude"
    CODEX = "codex"
    BOT = "bot"


class EventKind(StrEnum):
    MESSAGE = "message"
    OPINION = "opinion"
    DEBATE = "debate"
    DECISION = "decision"
    DESIGN = "design"
    IMPL = "impl"
    TEST = "test"
    REVIEW = "review"
    FIX = "fix"
    DOC_SYNC = "doc_sync"
    COMMAND = "command"
    ERROR = "error"


# 상태 전이와 함께 바꿀 수 있는 tasks 필드
UPDATABLE_FIELDS = frozenset(
    {
        "prev_state",
        "review_round",
        "test_retry",
        "opinion_rounds",
        "issue_number",
        "pr_number",
        "branch",
        "worktree",
        "claude_session",
        "waiting_since",
        "reminded_at",
    }
)


class StaleStateError(RuntimeError):
    """작업 상태가 예상과 다르다. 다른 코루틴이 먼저 상태를 바꿨다."""


class NotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class NewEvent:
    actor: Actor
    kind: EventKind
    payload: Any  # JSON으로 저장할 수 있는 값 (검증된 스키마 원본은 model_dump(mode="json"))
    discord_message: str | None = None


@dataclass(frozen=True)
class TaskRecord:
    id: int
    project: str
    discord_thread: str
    title: str
    state: TaskState
    prev_state: TaskState | None
    review_round: int
    test_retry: int
    opinion_rounds: int
    issue_number: int | None
    pr_number: int | None
    branch: str | None
    worktree: str | None
    claude_session: str | None
    waiting_since: str | None
    reminded_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class EventRecord:
    id: int
    task_id: int
    actor: Actor
    kind: EventKind
    payload: Any
    discord_message: str | None
    created_at: str


@dataclass(frozen=True)
class AgentRunRecord:
    id: str
    task_id: int
    agent: AgentName
    stage: Stage
    exit_code: int | None
    status: str  # running | ok | invalid_output | timeout | cancelled | error
    log_path: str | None
    started_at: str
    finished_at: str | None


RUNNING = "running"
INVALID_OUTPUT = "invalid_output"


class Repository:
    def __init__(self, conn: aiosqlite.Connection, clock: Clock):
        self._conn = conn
        self._clock = clock
        self._lock = asyncio.Lock()

    def _now(self) -> str:
        return to_iso(self._clock.now())

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[None]:
        async with self._lock:
            await self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                await self._conn.execute("ROLLBACK")
                raise
            await self._conn.execute("COMMIT")

    # tasks

    async def create_task(
        self,
        *,
        project: str,
        discord_thread: str,
        title: str,
        state: TaskState,
        event: NewEvent,
        updates: Mapping[str, object] | None = None,
    ) -> TaskRecord:
        fields = _checked_updates(updates or {})
        now = self._now()
        columns = ["project", "discord_thread", "title", "state", "created_at", "updated_at"]
        values: list[object] = [project, discord_thread, title, state.value, now, now]
        columns += list(fields)
        values += list(fields.values())
        async with self._transaction():
            cursor = await self._conn.execute(
                f"INSERT INTO tasks ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' for _ in columns)})",
                values,
            )
            task_id = cursor.lastrowid
            assert task_id is not None
            await self._insert_event(task_id, event, now)
        return await self.get_task(task_id)

    async def get_task(self, task_id: int) -> TaskRecord:
        row = await self._fetchone("SELECT * FROM tasks WHERE id = ?", (task_id,))
        if row is None:
            raise NotFoundError(f"작업 {task_id}가 없다")
        return _task(row)

    async def find_task_by_thread(self, discord_thread: str) -> TaskRecord | None:
        row = await self._fetchone(
            "SELECT * FROM tasks WHERE discord_thread = ?", (discord_thread,)
        )
        return None if row is None else _task(row)

    async def list_tasks(self, states: set[TaskState] | None = None) -> list[TaskRecord]:
        if states:
            marks = ", ".join("?" for _ in states)
            rows = await self._fetchall(
                f"SELECT * FROM tasks WHERE state IN ({marks}) ORDER BY id",
                [s.value for s in states],
            )
        else:
            rows = await self._fetchall("SELECT * FROM tasks ORDER BY id", ())
        return [_task(row) for row in rows]

    async def apply_transition(
        self,
        task_id: int,
        *,
        expected_state: TaskState,
        new_state: TaskState,
        event: NewEvent,
        updates: Mapping[str, object] | None = None,
    ) -> TaskRecord:
        """상태와 필드를 바꾸고 이벤트를 기록한다. 현재 상태가 expected_state가 아니면 실패한다."""
        fields = _checked_updates(updates or {})
        now = self._now()
        assignments = ["state = ?", "updated_at = ?"] + [f"{name} = ?" for name in fields]
        values: list[object] = [new_state.value, now, *fields.values(), task_id]
        values.append(expected_state.value)
        async with self._transaction():
            cursor = await self._conn.execute(
                f"UPDATE tasks SET {', '.join(assignments)} WHERE id = ? AND state = ?",
                values,
            )
            if cursor.rowcount != 1:
                current = await self._fetchone("SELECT state FROM tasks WHERE id = ?", (task_id,))
                if current is None:
                    raise NotFoundError(f"작업 {task_id}가 없다")
                raise StaleStateError(
                    f"작업 {task_id}의 상태가 {expected_state}가 아니라 {current['state']}이다"
                )
            await self._insert_event(task_id, event, now)
        return await self.get_task(task_id)

    # events

    async def add_event(self, task_id: int, event: NewEvent) -> EventRecord:
        now = self._now()
        async with self._transaction():
            event_id = await self._insert_event(task_id, event, now)
        row = await self._fetchone("SELECT * FROM events WHERE id = ?", (event_id,))
        assert row is not None
        return _event(row)

    async def list_events(
        self, task_id: int, kinds: set[EventKind] | None = None
    ) -> list[EventRecord]:
        sql = "SELECT * FROM events WHERE task_id = ?"
        params: list[object] = [task_id]
        if kinds:
            sql += f" AND kind IN ({', '.join('?' for _ in kinds)})"
            params += [k.value for k in kinds]
        rows = await self._fetchall(sql + " ORDER BY id", params)
        return [_event(row) for row in rows]

    async def _insert_event(self, task_id: int, event: NewEvent, now: str) -> int:
        cursor = await self._conn.execute(
            "INSERT INTO events (task_id, actor, kind, payload, discord_message, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                task_id,
                event.actor.value,
                event.kind.value,
                json.dumps(event.payload, ensure_ascii=False),
                event.discord_message,
                now,
            ),
        )
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    # agent_runs

    async def start_agent_run(
        self, run_id: str, *, task_id: int, agent: AgentName, stage: Stage
    ) -> AgentRunRecord:
        async with self._transaction():
            await self._conn.execute(
                "INSERT INTO agent_runs (id, task_id, agent, stage, status, started_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, task_id, agent, stage.value, RUNNING, self._now()),
            )
        return await self.get_agent_run(run_id)

    async def finish_agent_run(
        self,
        run_id: str,
        *,
        status: RunStatus | str,
        exit_code: int | None,
        log_path: str | None,
    ) -> AgentRunRecord:
        """status는 러너 결과(RunStatus) 또는 출력 검증 실패 시 INVALID_OUTPUT."""
        status_value = str(status)
        if status_value not in {s.value for s in RunStatus} | {INVALID_OUTPUT}:
            raise ValueError(f"알 수 없는 실행 상태: {status_value}")
        async with self._transaction():
            cursor = await self._conn.execute(
                "UPDATE agent_runs SET status = ?, exit_code = ?, log_path = ?, finished_at = ? "
                "WHERE id = ? AND status = ?",
                (status_value, exit_code, log_path, self._now(), run_id, RUNNING),
            )
            if cursor.rowcount != 1:
                raise StaleStateError(f"실행 {run_id}가 없거나 이미 끝났다")
        return await self.get_agent_run(run_id)

    async def get_agent_run(self, run_id: str) -> AgentRunRecord:
        row = await self._fetchone("SELECT * FROM agent_runs WHERE id = ?", (run_id,))
        if row is None:
            raise NotFoundError(f"실행 {run_id}가 없다")
        return AgentRunRecord(**{key: row[key] for key in row.keys()})

    async def list_running_agent_runs(self, task_id: int | None = None) -> list[AgentRunRecord]:
        sql, params = "SELECT * FROM agent_runs WHERE status = ?", [RUNNING]
        if task_id is not None:
            sql += " AND task_id = ?"
            params.append(task_id)
        rows = await self._fetchall(sql + " ORDER BY started_at", params)
        return [AgentRunRecord(**{key: row[key] for key in row.keys()}) for row in rows]

    # helpers

    async def _fetchone(self, sql: str, params: Any) -> aiosqlite.Row | None:
        async with self._conn.execute(sql, params) as cursor:
            return await cursor.fetchone()

    async def _fetchall(self, sql: str, params: Any) -> list[aiosqlite.Row]:
        async with self._conn.execute(sql, params) as cursor:
            return list(await cursor.fetchall())


def _checked_updates(updates: Mapping[str, object]) -> dict[str, object]:
    unknown = set(updates) - UPDATABLE_FIELDS
    if unknown:
        raise ValueError(f"바꿀 수 없는 필드: {', '.join(sorted(unknown))}")
    return {
        name: value.value if isinstance(value, StrEnum) else value
        for name, value in updates.items()
    }


def _task(row: aiosqlite.Row) -> TaskRecord:
    data = {key: row[key] for key in row.keys()}
    data["state"] = TaskState(data["state"])
    data["prev_state"] = TaskState(data["prev_state"]) if data["prev_state"] else None
    return TaskRecord(**data)


def _event(row: aiosqlite.Row) -> EventRecord:
    return EventRecord(
        id=row["id"],
        task_id=row["task_id"],
        actor=Actor(row["actor"]),
        kind=EventKind(row["kind"]),
        payload=json.loads(row["payload"]),
        discord_message=row["discord_message"],
        created_at=row["created_at"],
    )
