"""로컬 대시보드 테스트. 봇 저장소로 DB를 만들고 handle()로 각 주소를 확인한다."""

import asyncio
import sqlite3
from datetime import UTC, datetime
from http import HTTPStatus

import pytest

from bot.agents.base import RunStatus, Stage
from bot.clock import FixedClock
from bot.dashboard import queries
from bot.dashboard.server import DashboardSettings, handle
from bot.store import INVALID_OUTPUT, Actor, EventKind, NewEvent, Repository, connect
from bot.workflow.state import TaskState

T0 = datetime(2026, 10, 11, 9, 0, tzinfo=UTC)
OPINION = {
    "stance": "alternative",
    "conclusion": "tripId를 쓰자",
    "reasons": ["이미 있다"],
    "risks": ["노출 조건이 복잡해진다"],
    "proposal": "기간 기준으로만 노출",
}


@pytest.fixture
def settings(tmp_path):
    db = tmp_path / "zerosync.db"
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    async def build():
        conn = await connect(db)
        repo = Repository(conn, FixedClock(T0))
        try:
            first = await repo.create_task(
                project="gagaessi",
                discord_thread="111",
                title="여행 <소비>",
                state=TaskState.OPINIONS,
                event=NewEvent(
                    Actor.ZERO, EventKind.MESSAGE, {"title": "여행", "text": "<script>x</script>"}
                ),
            )
            await repo.add_event(
                first.id, NewEvent(Actor.CLAUDE, EventKind.OPINION, {"opinion": OPINION}, "m1")
            )
            await repo.add_event(
                first.id,
                NewEvent(
                    Actor.CODEX,
                    EventKind.ERROR,
                    {"reason": INVALID_OUTPUT, "error": "형식", "raw": "엉망"},
                ),
            )
            await repo.start_agent_run(
                "r-ok", task_id=first.id, agent="claude", stage=Stage.OPINION
            )
            log = runs_dir / "r-ok.log"
            log.write_text("run_id: r-ok\n전체 출력", encoding="utf-8")
            await repo.finish_agent_run("r-ok", status=RunStatus.OK, exit_code=0, log_path=str(log))
            await repo.start_agent_run(
                "r-bad", task_id=first.id, agent="codex", stage=Stage.OPINION
            )
            await repo.finish_agent_run(
                "r-bad", status=INVALID_OUTPUT, exit_code=0, log_path="/etc/passwd"
            )

            second = await repo.create_task(
                project="jday",
                discord_thread="222",
                title="다른 프로젝트",
                state=TaskState.OPINIONS,
                event=NewEvent(Actor.ZERO, EventKind.MESSAGE, {"title": "t", "text": "x"}),
            )
            await repo.apply_transition(
                second.id,
                expected_state=TaskState.OPINIONS,
                new_state=TaskState.STOPPED,
                event=NewEvent(Actor.ZERO, EventKind.COMMAND, {"name": "stop", "arg": ""}),
            )
            await repo.start_agent_run(
                "r-cancel", task_id=second.id, agent="claude", stage=Stage.DEBATE
            )
            await repo.finish_agent_run(
                "r-cancel", status=RunStatus.CANCELLED, exit_code=None, log_path=None
            )
        finally:
            await conn.close()

    asyncio.run(build())
    return DashboardSettings(db=db, runs_dir=runs_dir, guild_id="999")


def get(settings, path):
    response = handle(settings, path)
    return response.status, response.body


def test_summary_counts_across_projects(settings):
    conn = queries.open_readonly(settings.db)
    try:
        summaries = {s.project: s for s in queries.project_summaries(conn)}
        assert summaries["gagaessi"].tasks == 1
        assert summaries["gagaessi"].by_status == {"ok": 1, "invalid_output": 1}
        assert summaries["jday"].by_state == {"STOPPED": 1}
        stats = {(s.agent, s.stage): s for s in queries.stage_stats(conn)}
        assert stats[("claude", "opinion")].runs == 1
        assert stats[("claude", "debate")].by_status == {"cancelled": 1}
        # 평균은 성공한 실행만
        assert stats[("claude", "debate")].avg_sec is None
        assert stats[("claude", "opinion")].avg_sec == 0.0
    finally:
        conn.close()

    status, body = get(settings, "/")
    assert status is HTTPStatus.OK
    assert "gagaessi" in body and "jday" in body
    assert "형식 오류 1" in body


def test_task_list_filters_and_links(settings):
    _, body = get(settings, "/tasks")
    assert "#1 여행 &lt;소비&gt;" in body
    assert "#2 다른 프로젝트" in body
    assert "https://discord.com/channels/999/111" in body

    _, body = get(settings, "/tasks?project=jday")
    assert "#2 다른 프로젝트" in body and "#1 여행" not in body
    _, body = get(settings, "/tasks?state=OPINIONS")
    assert "#1 여행" in body and "#2 다른" not in body


def test_task_detail_escapes_content(settings):
    status, body = get(settings, "/tasks/1")
    assert status is HTTPStatus.OK
    assert "<script>x</script>" not in body
    assert "&lt;script&gt;x&lt;/script&gt;" in body
    assert "대안 제시 — tripId를 쓰자" in body
    assert "원문:\n엉망" in body
    assert "에이전트 실행 2회" in body


def test_runs_list_filters(settings):
    _, body = get(settings, "/runs")
    assert body.count('/log">보기</a>') == 2  # 로그 경로가 없는 실행은 링크가 없다
    _, body = get(settings, "/runs?status=cancelled")
    assert "취소" in body and "/runs/r-ok/log" not in body
    _, body = get(settings, "/runs?project=gagaessi")
    assert "다른 프로젝트" not in body


def test_log_is_served_only_from_runs_dir(settings):
    response = handle(settings, "/runs/r-ok/log")
    assert response.status is HTTPStatus.OK
    assert response.content_type.startswith("text/plain")
    assert response.body == "run_id: r-ok\n전체 출력"

    response = handle(settings, "/runs/r-bad/log")
    assert response.status is HTTPStatus.FORBIDDEN
    assert "root:" not in response.body

    assert handle(settings, "/runs/r-cancel/log").status is HTTPStatus.NOT_FOUND
    assert handle(settings, "/runs/nope/log").status is HTTPStatus.NOT_FOUND


def test_unknown_paths_are_404(settings):
    for path in ("/tasks/99", "/tasks/abc", "/nope", "/runs/r-ok"):
        assert handle(settings, path).status is HTTPStatus.NOT_FOUND


def test_database_is_opened_read_only(settings):
    conn = queries.open_readonly(settings.db)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM tasks")
    finally:
        conn.close()


def test_missing_database_shows_message(tmp_path):
    settings = DashboardSettings(db=tmp_path / "none.db", runs_dir=tmp_path)
    status, body = get(settings, "/")
    assert status is HTTPStatus.OK
    assert "봇을 한 번 실행하면 만들어진다" in body
    assert not (tmp_path / "none.db").exists()


def test_phase2_events_are_rendered(settings):
    from bot.testrun import TestReport

    async def add():
        conn = await connect(settings.db)
        repo = Repository(conn, FixedClock(T0))
        try:
            report = TestReport(RunStatus.OK, 0, 431, 0, duration_sec=700.0)
            await repo.add_event(1, NewEvent(Actor.BOT, EventKind.TEST, report.to_payload()))
            await repo.add_event(1, NewEvent(Actor.BOT, EventKind.MERGE, {"pr": 43}))
        finally:
            await conn.close()

    asyncio.run(add())
    _, body = get(settings, "/tasks/1")
    assert "테스트 통과 — 431개" in body
    assert "PR #43 merge 감지" in body
