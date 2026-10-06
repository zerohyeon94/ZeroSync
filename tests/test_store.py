import asyncio
from datetime import UTC, datetime, timedelta

import aiosqlite
import pytest

from bot.agents.base import RunStatus, Stage
from bot.clock import FixedClock, from_iso, to_iso
from bot.store import (
    INVALID_OUTPUT,
    RUNNING,
    SCHEMA_VERSION,
    Actor,
    EventKind,
    NewEvent,
    NotFoundError,
    Repository,
    SchemaVersionError,
    StaleStateError,
    connect,
    schema_version,
)
from bot.workflow.state import PostCreated, TaskState, ZeroMessage, start_task, transition

T0 = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


async def open_repo(path=":memory:", clock=None):
    conn = await connect(path)
    return conn, Repository(conn, clock or FixedClock(T0))


def zero(text, kind=EventKind.MESSAGE):
    return NewEvent(Actor.ZERO, kind, {"text": text})


async def new_task(repo, thread="thread-1"):
    result = start_task(PostCreated("예산 배너", "배너를 띄우자"))
    return await repo.create_task(
        project="gagessi",
        discord_thread=thread,
        title="예산 배너",
        state=result.state,
        event=zero("배너를 띄우자"),
        updates=result.updates,
    )


# 시각


def test_clock_iso_round_trip_in_utc():
    kst = datetime(2026, 10, 7, 18, 0, tzinfo=UTC).astimezone()
    assert to_iso(kst) == "2026-10-07T18:00:00+00:00"
    assert from_iso(to_iso(kst)) == datetime(2026, 10, 7, 18, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        to_iso(datetime(2026, 10, 7))
    with pytest.raises(ValueError):
        FixedClock(datetime(2026, 10, 7))


# 스키마


def test_connect_creates_schema_and_file(tmp_path):
    path = tmp_path / "nested" / "zerosync.db"

    async def scenario():
        conn = await connect(path)
        version = await schema_version(conn)
        async with conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'") as cur:
            tables = {row[0] for row in await cur.fetchall()}
        async with conn.execute("PRAGMA foreign_keys") as cur:
            fk = (await cur.fetchone())[0]
        await conn.close()
        return version, tables, fk

    version, tables, fk = run(scenario())
    assert path.exists()
    assert version == SCHEMA_VERSION == 1
    assert {"tasks", "events", "agent_runs"} <= tables
    assert fk == 1


def test_reconnect_keeps_data_and_does_not_migrate_twice(tmp_path):
    path = tmp_path / "zerosync.db"

    async def scenario():
        conn, repo = await open_repo(path)
        await new_task(repo)
        await conn.close()
        conn, repo = await open_repo(path)
        tasks = await repo.list_tasks()
        await conn.close()
        return tasks

    assert [t.title for t in run(scenario())] == ["예산 배너"]


def test_newer_schema_is_refused(tmp_path):
    path = tmp_path / "zerosync.db"

    async def scenario():
        conn = await aiosqlite.connect(path)
        await conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
        await conn.commit()
        await conn.close()
        await connect(path)

    with pytest.raises(SchemaVersionError):
        run(scenario())


# tasks + events


def test_create_task_records_first_event():
    async def scenario():
        conn, repo = await open_repo()
        task = await new_task(repo)
        events = await repo.list_events(task.id)
        found = await repo.find_task_by_thread("thread-1")
        await conn.close()
        return task, events, found

    task, events, found = run(scenario())
    assert task.state is TaskState.OPINIONS
    assert task.opinion_rounds == 0
    assert task.created_at == task.updated_at == "2026-10-07T09:00:00+00:00"
    assert found == task
    assert [(e.actor, e.kind, e.payload) for e in events] == [
        (Actor.ZERO, EventKind.MESSAGE, {"text": "배너를 띄우자"})
    ]


def test_duplicate_thread_is_rejected_without_partial_event():
    async def scenario():
        conn, repo = await open_repo()
        task = await new_task(repo)
        with pytest.raises(aiosqlite.IntegrityError):
            await new_task(repo)
        events = await repo.list_events(task.id)
        tasks = await repo.list_tasks()
        await conn.close()
        return events, tasks

    events, tasks = run(scenario())
    assert len(tasks) == 1
    assert len(events) == 1


def test_apply_transition_saves_state_fields_and_event_together():
    clock = FixedClock(T0)

    async def scenario():
        conn, repo = await open_repo(clock=clock)
        task = await new_task(repo)
        clock.advance(timedelta(minutes=5))
        result = transition(task, ZeroMessage("@codex 반례는?"))
        task = await repo.apply_transition(
            task.id,
            expected_state=task.state,
            new_state=result.state,
            event=zero("@codex 반례는?"),
            updates=result.updates,
        )
        events = await repo.list_events(task.id, {EventKind.MESSAGE})
        await conn.close()
        return task, events

    task, events = run(scenario())
    assert task.state is TaskState.OPINIONS
    assert task.opinion_rounds == 1
    assert task.updated_at == "2026-10-07T09:05:00+00:00"
    assert task.created_at == "2026-10-07T09:00:00+00:00"
    assert [e.payload["text"] for e in events] == ["배너를 띄우자", "@codex 반례는?"]


def test_apply_transition_with_wrong_expected_state_changes_nothing():
    async def scenario():
        conn, repo = await open_repo()
        task = await new_task(repo)
        with pytest.raises(StaleStateError, match="OPINIONS"):
            await repo.apply_transition(
                task.id,
                expected_state=TaskState.DESIGNING,
                new_state=TaskState.AWAIT_DESIGN_APPROVAL,
                event=NewEvent(Actor.BOT, EventKind.DESIGN, {}),
            )
        after = await repo.get_task(task.id)
        events = await repo.list_events(task.id)
        await conn.close()
        return after, events

    after, events = run(scenario())
    assert after.state is TaskState.OPINIONS
    assert len(events) == 1


def test_apply_transition_rejects_unknown_fields_and_missing_task():
    async def scenario():
        conn, repo = await open_repo()
        task = await new_task(repo)
        with pytest.raises(ValueError, match="state"):
            await repo.apply_transition(
                task.id,
                expected_state=task.state,
                new_state=task.state,
                event=zero("x"),
                updates={"state": "DONE"},
            )
        with pytest.raises(NotFoundError):
            await repo.apply_transition(
                999, expected_state=task.state, new_state=task.state, event=zero("x")
            )
        with pytest.raises(NotFoundError):
            await repo.get_task(999)
        await conn.close()

    run(scenario())


def test_prev_state_round_trips_as_enum():
    async def scenario():
        conn, repo = await open_repo()
        task = await new_task(repo)
        task = await repo.apply_transition(
            task.id,
            expected_state=TaskState.OPINIONS,
            new_state=TaskState.NEEDS_HUMAN,
            event=NewEvent(Actor.BOT, EventKind.ERROR, {"reason": "test"}),
            updates={"prev_state": TaskState.OPINIONS},
        )
        waiting = await repo.list_tasks({TaskState.NEEDS_HUMAN})
        await conn.close()
        return task, waiting

    task, waiting = run(scenario())
    assert task.prev_state is TaskState.OPINIONS
    assert [t.id for t in waiting] == [task.id]


def test_concurrent_transitions_only_one_wins():
    async def scenario():
        conn, repo = await open_repo()
        task = await new_task(repo)

        async def decide(n):
            return await repo.apply_transition(
                task.id,
                expected_state=TaskState.OPINIONS,
                new_state=TaskState.DESIGNING,
                event=zero(f"/decide {n}", EventKind.DECISION),
            )

        results = await asyncio.gather(decide(1), decide(2), return_exceptions=True)
        decisions = await repo.list_events(task.id, {EventKind.DECISION})
        await conn.close()
        return results, decisions

    results, decisions = run(scenario())
    assert sum(isinstance(r, StaleStateError) for r in results) == 1
    assert len(decisions) == 1


# agent_runs


def test_agent_run_lifecycle():
    async def scenario():
        conn, repo = await open_repo()
        task = await new_task(repo)
        started = await repo.start_agent_run(
            "run-1", task_id=task.id, agent="claude", stage=Stage.OPINION
        )
        await repo.start_agent_run("run-2", task_id=task.id, agent="codex", stage=Stage.OPINION)
        running = await repo.list_running_agent_runs(task.id)
        ok = await repo.finish_agent_run(
            "run-1", status=RunStatus.OK, exit_code=0, log_path="/runs/run-1.log"
        )
        invalid = await repo.finish_agent_run(
            "run-2", status=INVALID_OUTPUT, exit_code=0, log_path=None
        )
        with pytest.raises(StaleStateError):
            await repo.finish_agent_run("run-1", status=RunStatus.ERROR, exit_code=1, log_path=None)
        with pytest.raises(ValueError):
            await repo.finish_agent_run("run-2", status="weird", exit_code=0, log_path=None)
        left = await repo.list_running_agent_runs()
        await conn.close()
        return started, running, ok, invalid, left

    started, running, ok, invalid, left = run(scenario())
    assert started.status == RUNNING and started.finished_at is None
    assert [r.id for r in running] == ["run-1", "run-2"]
    assert (ok.status, ok.exit_code, ok.log_path) == ("ok", 0, "/runs/run-1.log")
    assert ok.finished_at is not None
    assert invalid.status == "invalid_output"
    assert left == []


def test_agent_run_requires_existing_task():
    async def scenario():
        conn, repo = await open_repo()
        with pytest.raises(aiosqlite.IntegrityError):
            await repo.start_agent_run("run-1", task_id=999, agent="claude", stage=Stage.OPINION)
        await conn.close()

    run(scenario())
