"""워크플로 엔진 통합 테스트 (SPEC 12.3).

에이전트(FakeAgentRunner), 채팅(FakeChatIO), 저장소(메모리 SQLite), 시각(FixedClock)을
가짜로 두고 OPINIONS 단계 한 사이클을 시뮬레이션한다.
"""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bot.agents import AgentRequest, AgentResult, FakeAgentRunner, RunStatus, Stage
from bot.clock import FixedClock
from bot.store import EventKind, Repository, connect
from bot.workflow.chat import FakeChatIO
from bot.workflow.engine import Engine
from bot.workflow.state import CommandName, TaskState

T0 = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
REPO = Path("/repos/gagessi")
THREAD = "thread-1"


def opinion(conclusion, stance="agree"):
    return json.dumps(
        {
            "stance": stance,
            "conclusion": conclusion,
            "reasons": ["근거"],
            "risks": ["위험"],
            "proposal": "제안",
        },
        ensure_ascii=False,
    )


def failed(status=RunStatus.TIMEOUT):
    return AgentResult(status, None, "", "시간 초과", None, 1.0, Path("runs/x.log"))


class Harness:
    def __init__(self, conn, claude, codex):
        self.conn = conn
        self.repo = Repository(conn, FixedClock(T0))
        self.chat = FakeChatIO()
        self.claude, self.codex = claude, codex
        self.engine = Engine(
            self.repo,
            self.chat,
            {"claude": claude, "codex": codex},
            {"gagessi": REPO},
            timeout_sec=60,
        )

    async def post(self, text="예산 초과 시 배너를 띄우자"):
        return await self.engine.on_post(
            project="gagessi", thread=THREAD, title="예산 배너", text=text
        )

    async def task(self):
        return await self.repo.find_task_by_thread(THREAD)

    async def events(self, *kinds):
        task = await self.task()
        return await self.repo.list_events(task.id, set(kinds) or None)

    async def runs(self):
        rows = await self.conn.execute_fetchall("SELECT agent, stage, status FROM agent_runs")
        return sorted(tuple(row) for row in rows)


def scenario(claude=(), codex=()):
    """claude·codex 응답 목록으로 Harness를 만들어 시나리오 함수를 실행한다."""

    def wrap(body):
        async def main():
            conn = await connect(":memory:")
            try:
                h = Harness(
                    conn, FakeAgentRunner("claude", claude), FakeAgentRunner("codex", codex)
                )
                return await body(h)
            finally:
                await conn.close()

        return asyncio.run(main())

    return wrap


# 게시글 → 첫 의견


def test_post_creates_task_and_posts_both_opinions():
    @scenario(claude=[opinion("Beta 의견")], codex=[opinion("Alpha 의견", "oppose")])
    async def result(h):
        task = await h.post()
        assert task.state is TaskState.OPINIONS

        for runner in (h.claude, h.codex):
            (req,) = runner.requests
            assert req.stage is Stage.OPINION
            assert req.mode == "read_only"
            assert req.cwd == REPO
            assert req.output_schema["title"] == "Opinion"
            # 첫 의견은 상대 의견 없이 독립 작성
            assert "지금까지의 흐름" not in req.prompt
            assert "예산 초과 시 배너를 띄우자" in req.prompt

        authors = [(p.author, p.mention) for p in h.chat.posts]
        # Beta, Alpha 순서. 둘 다 도착한 마지막 게시에서만 멘션
        assert authors == [("claude", False), ("codex", True)]
        assert "**찬성** — Beta 의견" in h.chat.posts[0].text
        assert "**반대** — Alpha 의견" in h.chat.posts[1].text

        opinions = await h.events(EventKind.OPINION)
        assert [e.actor.value for e in opinions] == ["claude", "codex"]
        assert [e.discord_message for e in opinions] == ["msg-1", "msg-2"]
        assert opinions[0].payload["first"] is True
        assert await h.runs() == [("claude", "opinion", "ok"), ("codex", "opinion", "ok")]

    assert result is None


def test_duplicate_post_and_unknown_thread_are_ignored():
    @scenario(claude=[opinion("a")], codex=[opinion("b")])
    async def _(h):
        await h.post()
        assert await h.post() is None
        await h.engine.on_message("other-thread", "안녕")
        await h.engine.on_command("other-thread", CommandName.STOP)
        assert len(h.chat.posts) == 2
        with pytest.raises(ValueError, match="알 수 없는 프로젝트"):
            await h.engine.on_post(project="nope", thread="t2", title="x", text="y")


# 추가 질문


def test_follow_up_question_sends_history_to_both():
    @scenario(claude=[opinion("a1"), opinion("a2")], codex=[opinion("b1"), opinion("b2")])
    async def _(h):
        await h.post()
        await h.engine.on_message(THREAD, "배너 대신 푸시 알림은?", message_id="m-zero")

        for runner, other in ((h.claude, "Alpha · Codex"), (h.codex, "Beta · Claude")):
            prompt = runner.requests[1].prompt
            assert "지금까지의 흐름" in prompt
            assert other in prompt  # 두 번째 질문부터 상대 의견도 함께 전달
            assert "배너 대신 푸시 알림은?" in prompt

        task = await h.task()
        assert task.opinion_rounds == 1
        message = (await h.events(EventKind.MESSAGE))[-1]
        assert message.discord_message == "m-zero"
        assert h.chat.posts[-1].mention is True


def test_targeted_question_calls_only_that_agent():
    @scenario(claude=[opinion("a1")], codex=[opinion("b1"), opinion("b2")])
    async def _(h):
        await h.post()
        await h.engine.on_message(THREAD, "@codex 더 작게 만들 수 있나?")
        assert len(h.claude.requests) == 1
        assert len(h.codex.requests) == 2
        assert "Zero의 질문:\n더 작게 만들 수 있나?" in h.codex.requests[1].prompt
        assert [(p.author, p.mention) for p in h.chat.posts[-1:]] == [("codex", True)]


def test_notice_after_more_than_five_questions():
    replies = [opinion(f"c{i}") for i in range(7)]

    @scenario(claude=replies, codex=[opinion("b")])
    async def _(h):
        await h.post()
        for i in range(6):
            await h.engine.on_message(THREAD, f"@claude 질문 {i}")
        notices = [p for p in h.chat.posts if p.author == "bot"]
        assert len(notices) == 1
        assert "/decide 대기 중" in notices[0].text
        assert notices[0].mention is False


# 형식 오류와 실행 실패


def test_format_error_is_retried_once_with_error():
    @scenario(claude=["그냥 문장", opinion("고친 의견")], codex=[opinion("b")])
    async def _(h):
        await h.post()
        retry = h.claude.requests[1].prompt
        assert "이전 출력의 형식 오류" in retry
        assert "```json 코드 블록을 찾지 못했다" in retry
        assert "고친 의견" in h.chat.posts[0].text
        assert await h.runs() == [
            ("claude", "opinion", "invalid_output"),
            ("claude", "opinion", "ok"),
            ("codex", "opinion", "ok"),
        ]


def test_repeated_format_error_posts_raw_and_keeps_opinions():
    @scenario(claude=["엉망 1", "엉망 2"], codex=[opinion("b")])
    async def _(h):
        await h.post()
        beta, alpha = h.chat.posts
        assert beta.author == "claude"
        assert "**형식 오류**" in beta.text
        assert "엉망 2" in beta.text
        assert (beta.mention, alpha.mention) == (False, True)
        (error,) = await h.events(EventKind.ERROR)
        assert error.payload["reason"] == "invalid_output"
        assert error.payload["raw"] == "엉망 2"
        # 운영 규약 2.1: 원문 게시 + 알림. 의견 단계는 그대로 (2026-10-10 Zero 결정)
        assert (await h.task()).state is TaskState.OPINIONS
        assert len(h.claude.requests) == 2


def test_cli_failure_posts_notice_and_alerts_ops():
    @scenario(claude=[opinion("a")], codex=[failed()])
    async def _(h):
        await h.post()
        beta, notice = h.chat.posts
        # 실패 안내도 Alpha 자리에 게시하고, 마지막 게시에서 멘션한다
        assert beta.author == "claude" and beta.mention is False
        assert notice.author == "bot" and notice.mention is True
        assert "Alpha · Codex" in notice.text and "timeout" in notice.text
        ((text, mention),) = h.chat.ops
        assert mention is True
        assert "timeout" in text and "runs/x.log" in text
        # 실행 실패는 재요청하지 않는다
        assert len(h.codex.requests) == 1
        assert ("codex", "opinion", "timeout") in await h.runs()


def test_both_failed_mentions_on_last_notice():
    @scenario(claude=[failed(RunStatus.ERROR)], codex=[failed()])
    async def _(h):
        await h.post()
        assert [(p.author, p.mention) for p in h.chat.posts] == [("bot", False), ("bot", True)]
        assert len(h.chat.ops) == 2


# /debate


def test_debate_sends_opponent_opinion():
    @scenario(
        claude=[opinion("Beta 첫 의견"), opinion("Beta 반박")],
        codex=[opinion("Alpha 첫 의견", "oppose"), opinion("Alpha 반박", "conditional")],
    )
    async def _(h):
        await h.post()
        await h.engine.on_command(THREAD, CommandName.DEBATE)
        claude_req = h.claude.requests[1]
        assert claude_req.stage is Stage.DEBATE
        assert "## Alpha · Codex의 직전 의견" in claude_req.prompt
        assert "Alpha 첫 의견" in claude_req.prompt
        assert "## 너의 직전 의견" in claude_req.prompt
        assert "Beta 첫 의견" in claude_req.prompt
        assert "Beta 첫 의견" in h.codex.requests[1].prompt

        beta, alpha = h.chat.posts[2:]
        assert beta.text.startswith("반박 · **찬성** — Beta 반박")
        assert alpha.mention is True
        debates = await h.events(EventKind.DEBATE)
        assert [e.actor.value for e in debates] == ["claude", "codex"]
        # 질문 수에 세지 않는다
        assert (await h.task()).opinion_rounds == 0


def test_debate_needs_both_opinions():
    @scenario(claude=[opinion("a")], codex=[failed()])
    async def _(h):
        await h.post()
        await h.engine.on_command(THREAD, CommandName.DEBATE)
        assert "의견이 없는 쪽: Alpha · Codex" in h.chat.posts[-1].text
        assert len(h.claude.requests) == 1


# /decide


def test_decide_records_decision_and_stops_before_phase_2():
    @scenario(claude=[opinion("a")], codex=[opinion("b")])
    async def _(h):
        await h.post()
        await h.engine.on_command(THREAD, CommandName.DECIDE, "  배너로 간다  ")
        task = await h.task()
        assert task.state is TaskState.DESIGNING
        (decision,) = await h.events(EventKind.DECISION)
        assert decision.payload == {"text": "배너로 간다"}
        notice = h.chat.posts[-1]
        assert notice.author == "bot" and notice.mention is False
        assert "결정을 기록했다" in notice.text

        await h.engine.on_message(THREAD, "추가 질문")
        assert "현재 상태: DESIGNING" in h.chat.posts[-1].text
        assert len(h.claude.requests) == 1


def test_decide_without_direction_is_rejected():
    @scenario(claude=[opinion("a")], codex=[opinion("b")])
    async def _(h):
        await h.post()
        await h.engine.on_command(THREAD, CommandName.DECIDE, "  ")
        assert (await h.task()).state is TaskState.OPINIONS
        assert "/decide 뒤에 방향을 적어야 한다" in h.chat.posts[-1].text
        (command,) = await h.events(EventKind.COMMAND)
        assert command.payload == {"name": "decide", "arg": "  "}


# /stop


class BlockingRunner:
    """cancel될 때까지 끝나지 않는 러너."""

    def __init__(self, name):
        self.name = name
        self.started = asyncio.Event()
        self.cancelled: list[str] = []
        self._release = asyncio.Event()

    async def run(self, request: AgentRequest) -> AgentResult:
        self.started.set()
        await self._release.wait()
        return AgentResult(RunStatus.CANCELLED, None, "", "", None, 0.0, Path("x.log"))

    async def cancel(self, run_id: str) -> None:
        self.cancelled.append(run_id)
        self._release.set()


def test_stop_cancels_running_agents_and_drops_results():
    async def main():
        conn = await connect(":memory:")
        try:
            h = Harness(conn, BlockingRunner("claude"), FakeAgentRunner("codex", [opinion("b")]))
            posting = asyncio.create_task(h.post())
            await h.claude.started.wait()
            await h.engine.on_command(THREAD, CommandName.STOP)
            await posting

            assert (await h.task()).state is TaskState.STOPPED
            assert len(h.claude.cancelled) == 1
            # 중지 안내만 남고 의견·실패 안내는 게시하지 않는다
            assert [p.author for p in h.chat.posts] == ["bot"]
            assert "작업을 중지했다" in h.chat.posts[0].text
            assert h.chat.ops == []
            assert ("claude", "opinion", "cancelled") in await h.runs()
            assert await h.events(EventKind.OPINION) == []

            await h.engine.on_message(THREAD, "다시")
            assert "현재 상태: STOPPED" in h.chat.posts[-1].text
        finally:
            await conn.close()

    asyncio.run(main())


def test_unimplemented_command_gets_notice():
    @scenario(claude=[opinion("a")], codex=[opinion("b")])
    async def _(h):
        task = await h.post()
        from bot.store import Actor, NewEvent

        await h.repo.apply_transition(
            task.id,
            expected_state=TaskState.OPINIONS,
            new_state=TaskState.NEEDS_HUMAN,
            event=NewEvent(Actor.BOT, EventKind.ERROR, {}),
        )
        await h.engine.on_command(THREAD, CommandName.RESUME)
        assert "아직 구현되지 않은 명령" in h.chat.posts[-1].text
        assert (await h.task()).state is TaskState.NEEDS_HUMAN
