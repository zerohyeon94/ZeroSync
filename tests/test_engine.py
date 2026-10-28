"""워크플로 엔진 통합 테스트 (SPEC 12.3).

에이전트(FakeAgentRunner), 채팅(FakeChatIO), GitHub(FakeGitHub), git(FakeGit), 테스트 실행,
저장소(메모리 SQLite), 시각(FixedClock)을 가짜로 두고 사이클을 시뮬레이션한다.
"""

import asyncio
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from orgs import LEGACY_ORG

from bot.agents import AgentRequest, AgentResult, FakeAgentRunner, RunStatus, Stage
from bot.clock import FixedClock
from bot.github.fake import FakeGit, FakeGitHub
from bot.store import EventKind, Repository, connect
from bot.testrun import TestReport
from bot.workflow.chat import FakeChatIO
from bot.workflow.engine import Engine, ProjectContext
from bot.workflow.state import CommandName, TaskState

T0 = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
REPO = Path("/repos/gagaessi")
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


DESIGN = {
    "change_type": "feature_change",
    "target_feature": "예산 배너",
    "slug": "budget-banner",
    "title": "월 예산 초과 시 홈 화면 배너 표시",
    "scope": "budget",
    "summary": "홈 화면에 초과 배너를 띄운다",
    "changes": ["HomeView 배너"],
    "test_plan": ["경계 테스트"],
    "risks": [],
    "design_doc": "docs/설계/42-budget-banner.md",
}


def design_reply(git=None, *, commit="docs(design): 배너 설계\n\nRefs: #42", **overrides):
    """설계 파일을 쓰고 커밋한 뒤 설계 JSON을 돌려주는 가짜 Beta."""
    data = {**DESIGN, **overrides}

    def respond(request):
        doc = request.cwd / data["design_doc"]
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text("설계 전문", encoding="utf-8")
        respond.git.add_commit(request.cwd, commit)
        return json.dumps(data, ensure_ascii=False)

    respond.git = git
    return respond


def work_reply(message="feat(budget): 배너 추가\n\nRefs: #42", responses=()):
    """커밋을 하나 쌓고 구현 보고를 돌려주는 가짜 Beta."""

    def respond(request):
        respond.git.add_commit(request.cwd, message)
        return json.dumps(
            {
                "changes_summary": "배너를 추가했다",
                "design_intent": "홈에서 바로 보이게",
                "check_points": ["경계 시각"],
                "responses": list(responses),
            },
            ensure_ascii=False,
        )

    respond.git = None
    return respond


def review_reply(required=0, recommended=0):
    findings = [
        {"severity": "required", "file": "HomeView.swift", "line": 3, "problem": f"필수 {i}",
         "reason": "버그", "suggestion": "고친다"}
        for i in range(1, required + 1)
    ] + [
        {"severity": "recommended", "file": None, "line": None, "problem": f"권장 {i}",
         "reason": "가독성", "suggestion": "다듬는다"}
        for i in range(1, recommended + 1)
    ]  # fmt: skip
    verdict = "CHANGES_REQUESTED" if required else "APPROVED"
    return json.dumps(
        {"verdict": verdict, "summary": "검토했다", "findings": findings}, ensure_ascii=False
    )


def make_report(passed=True, failed=()):
    status = RunStatus.OK if passed else RunStatus.ERROR
    return TestReport(
        status=status,
        exit_code=0 if passed else 65,
        total=10,
        failures=0 if passed else len(failed) or 1,
        failed_tests=list(failed),
        duration_sec=3.0,
        log_path="runs/test.log",
    )


class FakeTests:
    def __init__(self, reports=()):
        self.reports = list(reports)
        self.runs = []
        self.cancelled = []

    async def run(self, run_id, argv, *, cwd):
        self.runs.append((run_id, tuple(argv), cwd))
        return self.reports.pop(0) if self.reports else make_report()

    async def cancel(self, run_id):
        self.cancelled.append(run_id)


class Harness:
    def __init__(self, conn, claude, codex, tmp, tests=None):
        self.conn = conn
        self.tmp = tmp
        self.repo = Repository(conn, FixedClock(T0))
        self.chat = FakeChatIO()
        self.claude, self.codex = claude, codex
        self.github = FakeGitHub(repo="zerohyeon94/GagaeSsi")
        self.git = FakeGit()
        self.tests = tests or FakeTests()
        self.features = tmp / "기능"
        self.features.mkdir()
        (self.features / "예산 배너.md").write_text("기능")
        self.engine = Engine(
            self.repo,
            self.chat,
            {"claude": claude, "codex": codex},
            {
                "gagaessi": ProjectContext(
                    repo=REPO,
                    test_command=("xcodebuild", "test"),
                    github=self.github,
                    feature_dir=self.features,
                )
            },
            timeout_sec=60,
            org=LEGACY_ORG,
            git=self.git,
            tests=self.tests,
            worktrees_dir=tmp / "worktrees",
            thread_url=lambda thread: f"https://discord.com/channels/1/{thread}",
        )
        # 가짜 Beta 응답이 같은 FakeGit에 커밋을 쌓게 한다
        for runner in (claude, codex):
            for response in getattr(runner, "_responses", []):
                if getattr(response, "git", "unset") is None:
                    response.git = self.git

    async def post(self, text="예산 초과 시 배너를 띄우자"):
        return await self.engine.on_post(
            project="gagaessi", thread=THREAD, title="예산 배너", text=text
        )

    async def task(self):
        return await self.repo.find_task_by_thread(THREAD)

    async def events(self, *kinds):
        task = await self.task()
        return await self.repo.list_events(task.id, set(kinds) or None)

    async def runs(self):
        rows = await self.conn.execute_fetchall("SELECT agent, stage, status FROM agent_runs")
        return sorted(tuple(row) for row in rows)


def scenario(claude=(), codex=(), tests=None):
    """claude·codex 응답 목록으로 Harness를 만들어 시나리오 함수를 실행한다."""

    def wrap(body):
        async def main():
            conn = await connect(":memory:")
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    h = Harness(
                        conn,
                        FakeAgentRunner("claude", claude),
                        FakeAgentRunner("codex", codex),
                        Path(tmp),
                        FakeTests(tests or ()),
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
        assert authors == [("beta", False), ("alpha", True)]
        assert "**찬성** — Beta 의견" in h.chat.posts[0].text
        assert "**반대** — Alpha 의견" in h.chat.posts[1].text

        opinions = await h.events(EventKind.OPINION)
        assert [e.actor for e in opinions] == ["beta", "alpha"]
        assert [e.discord_message for e in opinions] == ["msg-1", "msg-2"]
        assert opinions[0].payload["first"] is True
        assert await h.runs() == [("alpha", "opinion", "ok"), ("beta", "opinion", "ok")]

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

        for runner, other in ((h.claude, "Alpha · 개발팀장"), (h.codex, "Beta · 기획팀장")):
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
        await h.engine.on_message(THREAD, "@alpha 더 작게 만들 수 있나?")
        assert len(h.claude.requests) == 1
        assert len(h.codex.requests) == 2
        assert "Zero의 질문:\n더 작게 만들 수 있나?" in h.codex.requests[1].prompt
        assert [(p.author, p.mention) for p in h.chat.posts[-1:]] == [("alpha", True)]


def test_notice_after_more_than_five_questions():
    replies = [opinion(f"c{i}") for i in range(7)]

    @scenario(claude=replies, codex=[opinion("b")])
    async def _(h):
        await h.post()
        for i in range(6):
            await h.engine.on_message(THREAD, f"@beta 질문 {i}")
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
            ("alpha", "opinion", "ok"),
            ("beta", "opinion", "invalid_output"),
            ("beta", "opinion", "ok"),
        ]


def test_repeated_format_error_posts_raw_and_keeps_opinions():
    @scenario(claude=["엉망 1", "엉망 2"], codex=[opinion("b")])
    async def _(h):
        await h.post()
        beta, alpha = h.chat.posts
        assert beta.author == "beta"
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
        assert beta.author == "beta" and beta.mention is False
        assert notice.author == "bot" and notice.mention is True
        assert "Alpha · 개발팀장" in notice.text and "timeout" in notice.text
        ((text, mention),) = h.chat.ops
        assert mention is True
        assert "timeout" in text and "runs/x.log" in text
        # 실행 실패는 재요청하지 않는다
        assert len(h.codex.requests) == 1
        assert ("alpha", "opinion", "timeout") in await h.runs()


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
        assert "## Alpha · 개발팀장의 직전 의견" in claude_req.prompt
        assert "Alpha 첫 의견" in claude_req.prompt
        assert "## 너의 직전 의견" in claude_req.prompt
        assert "Beta 첫 의견" in claude_req.prompt
        assert "Beta 첫 의견" in h.codex.requests[1].prompt

        beta, alpha = h.chat.posts[2:]
        assert beta.text.startswith("반박 · **찬성** — Beta 반박")
        assert alpha.mention is True
        debates = await h.events(EventKind.DEBATE)
        assert [e.actor for e in debates] == ["beta", "alpha"]
        # 질문 수에 세지 않는다
        assert (await h.task()).opinion_rounds == 0


def test_debate_needs_both_opinions():
    @scenario(claude=[opinion("a")], codex=[failed()])
    async def _(h):
        await h.post()
        await h.engine.on_command(THREAD, CommandName.DEBATE)
        assert "의견이 없는 쪽: Alpha · 개발팀장" in h.chat.posts[-1].text
        assert len(h.claude.requests) == 1


# /decide


def test_decide_creates_issue_and_starts_design():
    @scenario(claude=[opinion("a"), design_reply()], codex=[opinion("b")])
    async def _(h):
        await h.post()
        await h.engine.on_command(THREAD, CommandName.DECIDE, "  배너로 간다  ")
        (decision,) = await h.events(EventKind.DECISION)
        assert decision.payload == {"text": "배너로 간다"}

        # Issue는 봇이 기존 텍스트로 조립한다 (운영 규약 1.8)
        ((_, number, title, body, labels),) = h.github.named("create_issue")
        assert (number, title, labels) == (42, "예산 배너", ("zerosync",))
        assert "## 결정\n\n배너로 간다" in body
        assert "예산 초과 시 배너를 띄우자" in body
        assert "https://discord.com/channels/1/thread-1" in body
        notice = next(p for p in h.chat.posts if "Issue #42" in p.text)
        assert "결정을 기록하고" in notice.text and notice.mention is False

        request = h.claude.requests[1]
        assert request.stage is Stage.DESIGN
        assert request.mode == "write_worktree"
        assert request.cwd == h.tmp / "worktrees" / "gagaessi-42"
        assert "예산 배너" in request.prompt  # 기능 정의서 목록
        task = await h.task()
        assert task.state is TaskState.AWAIT_DESIGN_APPROVAL
        assert task.issue_number == 42

        await h.engine.on_message(THREAD, "추가 질문")
        assert "현재 상태: AWAIT_DESIGN_APPROVAL" in h.chat.posts[-1].text


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
            tmp = tempfile.TemporaryDirectory()
            h = Harness(
                conn,
                BlockingRunner("claude"),
                FakeAgentRunner("codex", [opinion("b")]),
                Path(tmp.name),
            )
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
            assert ("beta", "opinion", "cancelled") in await h.runs()
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
            new_state=TaskState.AWAIT_DOC_APPROVAL,
            event=NewEvent(Actor.BOT, EventKind.ERROR, {}),
        )
        # 문서 반영은 Phase 3
        await h.engine.on_command(THREAD, CommandName.APPROVE)
        assert "아직 구현되지 않은 명령" in h.chat.posts[-1].text
        assert (await h.task()).state is TaskState.AWAIT_DOC_APPROVAL


# 재시작 복구 (SPEC 3.4, Q8)


def test_recover_interrupted_runs():
    @scenario(claude=[opinion("a"), opinion("a2")], codex=[opinion("b"), opinion("b2")])
    async def _(h):
        task = await h.post()
        # 재시작 전에 끝나지 않은 실행이 남았다
        await h.repo.start_agent_run("left-1", task_id=task.id, agent="codex", stage=Stage.OPINION)
        other = await h.engine.on_post(project="gagaessi", thread="t2", title="두 번째", text="x")
        from bot.store import Actor, NewEvent

        await h.repo.apply_transition(
            other.id,
            expected_state=TaskState.OPINIONS,
            new_state=TaskState.DESIGNING,
            event=NewEvent(Actor.ZERO, EventKind.DECISION, {"text": "간다"}),
        )
        await h.repo.start_agent_run("left-2", task_id=other.id, agent="claude", stage=Stage.DESIGN)
        h.chat.posts.clear()

        await h.engine.recover_interrupted()

        assert await h.repo.list_running_agent_runs() == []
        # OPINIONS는 실패 안내 후 그대로
        assert (await h.task()).state is TaskState.OPINIONS
        first, second = h.chat.posts
        assert first.thread == THREAD and "봇 재시작으로 중단" in first.text
        assert first.mention is True
        # 그 밖의 진행 중 단계는 NEEDS_HUMAN
        moved = await h.repo.get_task(other.id)
        assert moved.state is TaskState.NEEDS_HUMAN
        assert moved.prev_state is TaskState.DESIGNING
        assert second.thread == "t2" and "재시작" in second.text and second.mention is True
        assert len(h.chat.ops) == 2 and all(mention for _, mention in h.chat.ops)


# Phase 2: 설계부터 merge까지 (SPEC 12.3 한 사이클 통합 테스트)


WT = "worktrees/gagaessi-42"


def test_full_cycle_from_decide_to_merge():
    @scenario(
        claude=[
            opinion("a"),
            design_reply(),
            work_reply(),
            work_reply("fix(budget): 테스트 실패 수정\n\nRefs: #42"),
            work_reply(
                "fix(budget): 리뷰 1라운드 [필수] 1 반영\n\nRefs: #42",
                responses=[{"index": 1, "action": "fixed", "note": "고쳤다"}],
            ),
        ],
        codex=[opinion("b"), review_reply(required=1, recommended=1), review_reply(recommended=1)],
        tests=[
            make_report(passed=False, failed=["BudgetTests testOver"]),
            make_report(),
            make_report(),
        ],
    )
    async def _(h):
        await h.post()
        await h.engine.on_command(THREAD, CommandName.DECIDE, "배너로 간다")
        task = await h.task()
        assert task.state is TaskState.AWAIT_DESIGN_APPROVAL
        assert task.branch == "feat/42-budget-banner"
        worktree = h.tmp / WT
        assert h.git.named("create_branch") == [
            ("create_branch", worktree, "feat/42-budget-banner")
        ]
        assert ("push", worktree, "feat/42-budget-banner") in h.git.calls
        design_post = next(p for p in h.chat.posts if p.text.startswith("**설계**"))
        assert design_post.author == "beta" and design_post.mention is True
        assert (
            "https://github.com/zerohyeon94/GagaeSsi/blob/feat/42-budget-banner/"
            "docs/설계/42-budget-banner.md" in design_post.text
        )
        assert h.github.named("comment_issue")[0][1] == 42

        await h.engine.on_command(THREAD, CommandName.APPROVE)

        task = await h.task()
        assert task.state is TaskState.AWAIT_MERGE
        # 설계 승인 시 type 라벨, PR은 테스트 통과 후 draft로 한 번만 만든다
        assert ("add_labels", 42, ("type:feature",)) in h.github.calls
        (pr,) = h.github.named("create_pr")
        assert pr[1:5] == (
            43,
            "develop",
            "feat/42-budget-banner",
            "feat(budget): 월 예산 초과 시 홈 화면 배너 표시",
        )
        assert "Refs #42" in pr[5] and "## 변경 요약" in pr[5]
        assert task.pr_number == 43
        # 테스트 실패 1회 → 수정, 리뷰 CHANGES_REQUESTED 1회 → 수정
        assert (task.test_retry, task.review_round) == (1, 1)
        assert len(h.tests.runs) == 3
        assert [r.stage for r in h.claude.requests[1:]] == [
            Stage.DESIGN,
            Stage.IMPLEMENT,
            Stage.FIX,
            Stage.FIX,
        ]
        fix_prompts = [r.prompt for r in h.claude.requests[3:]]
        assert "BudgetTests testOver" in fix_prompts[0]
        assert "필수 1" in fix_prompts[1] and "참고: [권장] 지적" in fix_prompts[1]
        # 구현·수정 단계는 설계 세션을 이어 쓴다
        assert all(r.mode == "write_worktree" for r in h.claude.requests[1:])
        # 2라운드 리뷰는 이전 [필수] 지적 해결 여부를 확인한다
        second_review = h.codex.requests[2].prompt
        assert "이전 라운드 [필수] 지적" in second_review and "리뷰 라운드: 2" in second_review
        assert h.codex.requests[1].mode == "read_only"
        assert len(h.github.named("comment_pr")) == 2
        assert h.github.named("mark_ready") == [("mark_ready", 43)]
        approved = h.chat.posts[-1]
        assert "APPROVED" in approved.text and approved.mention is True
        assert "남은 [권장] 1개" in approved.text
        # push는 모두 작업 브랜치로만
        assert {call[2] for call in h.git.named("push")} == {"feat/42-budget-banner"}

        # merge 감지
        from bot.github.client import PrState

        h.github.pr_states[43] = PrState("MERGED", True)
        await h.engine.poll_merges()
        task = await h.task()
        assert task.state is TaskState.DONE
        (close,) = h.github.named("close_issue")
        assert close[1:3] == (42, False)
        assert h.git.named("remove_worktree")
        assert "merge를 확인" in h.chat.posts[-1].text

        mentions = [p for p in h.chat.posts if p.mention]
        # 의견 도착, 설계 완료, 최종 확인에서만 멘션 (운영 규약 2.5)
        assert len(mentions) == 3


def test_design_commit_problem_is_retried_then_needs_human():
    bad = "설계 추가"  # 형식 위반

    @scenario(
        claude=[opinion("a"), design_reply(commit=bad), design_reply(commit=bad)],
        codex=[opinion("b")],
    )
    async def _(h):
        await h.post()
        await h.engine.on_command(THREAD, CommandName.DECIDE, "간다")
        retry = h.claude.requests[2].prompt
        assert "이전 출력의 형식 오류" in retry and "형식이 아니다" in retry
        task = await h.task()
        assert task.state is TaskState.NEEDS_HUMAN
        assert task.prev_state is TaskState.DESIGNING
        assert ("add_labels", 42, ("needs-human",)) in h.github.calls
        assert h.chat.posts[-1].mention is True
        assert "/resume" in h.chat.posts[-1].text
        # 브랜치를 만들지 않았으므로 push도 없다
        assert h.git.named("push") == []


def test_test_failure_limit_then_resume_adds_one_more_try():
    failing = [make_report(passed=False) for _ in range(4)]

    @scenario(
        claude=[opinion("a"), design_reply(), work_reply()]
        + [work_reply(f"fix: 테스트 수정 {i}\n\nRefs: #42") for i in range(3)],
        codex=[opinion("b")],
        tests=failing,
    )
    async def _(h):
        await h.post()
        await h.engine.on_command(THREAD, CommandName.DECIDE, "간다")
        await h.engine.on_command(THREAD, CommandName.APPROVE)
        task = await h.task()
        # 2회 초과(3번째 실패)에서 NEEDS_HUMAN (Q2)
        assert task.state is TaskState.NEEDS_HUMAN
        assert task.test_retry == 3
        assert len(h.tests.runs) == 3

        await h.engine.on_command(THREAD, CommandName.RESUME)
        task = await h.task()
        # 한도만 1회 늘고 카운터는 유지 → 수정 1회 더, 그 테스트도 실패하면 다시 NEEDS_HUMAN
        assert task.test_limit_bonus == 1
        assert task.state is TaskState.NEEDS_HUMAN
        assert task.test_retry == 4
        assert ("remove_label", 42, "needs-human") in h.github.calls


def test_revise_with_new_slug_renames_branch():
    @scenario(
        claude=[
            opinion("a"),
            design_reply(),
            design_reply(
                commit="docs(design): 설계 수정\n\nRefs: #42",
                change_type="bug_fix",
                slug="banner-fix",
                design_doc="docs/설계/42-banner-fix.md",
            ),
        ],
        codex=[opinion("b")],
    )
    async def _(h):
        await h.post()
        await h.engine.on_command(THREAD, CommandName.DECIDE, "간다")
        await h.engine.on_command(THREAD, CommandName.REVISE, "버그 수정으로 보자")
        task = await h.task()
        assert task.state is TaskState.AWAIT_DESIGN_APPROVAL
        assert task.branch == "fix/42-banner-fix"
        worktree = h.tmp / WT
        assert (
            "rename_branch",
            worktree,
            "feat/42-budget-banner",
            "fix/42-banner-fix",
        ) in h.git.calls
        assert ("delete_remote_branch", worktree, "feat/42-budget-banner") in h.git.calls
        revise_prompt = h.claude.requests[2].prompt
        assert "버그 수정으로 보자" in revise_prompt and "이전 설계 요약" in revise_prompt
        assert len(h.github.named("comment_issue")) == 2


def test_stop_after_design_closes_issue_and_deletes_branch():
    @scenario(claude=[opinion("a"), design_reply()], codex=[opinion("b")])
    async def _(h):
        await h.post()
        await h.engine.on_command(THREAD, CommandName.DECIDE, "간다")
        await h.engine.on_command(THREAD, CommandName.STOP)
        assert (await h.task()).state is TaskState.STOPPED
        (close,) = h.github.named("close_issue")
        assert close[1:3] == (42, True)  # not planned
        assert ("delete_remote_branch", h.tmp / WT, "feat/42-budget-banner") in h.git.calls
        assert h.git.named("remove_worktree")
        assert h.github.named("close_pr") == []


def test_fix_recommended_once_before_merge():
    @scenario(
        claude=[
            opinion("a"),
            design_reply(),
            work_reply(),
            work_reply("refactor: 권장 반영\n\nRefs: #42"),
        ],
        codex=[opinion("b"), review_reply(recommended=2), review_reply()],
    )
    async def _(h):
        await h.post()
        await h.engine.on_command(THREAD, CommandName.DECIDE, "간다")
        await h.engine.on_command(THREAD, CommandName.APPROVE)
        assert (await h.task()).state is TaskState.AWAIT_MERGE
        await h.engine.on_command(THREAD, CommandName.FIX, "권장 반영")
        prompt = h.claude.requests[-1].prompt
        assert "[권장] 지적 반영을 요청" in prompt and "권장 2" in prompt
        task = await h.task()
        assert task.state is TaskState.AWAIT_MERGE and task.recommended_fixed == 1
        await h.engine.on_command(THREAD, CommandName.FIX)
        assert "1회만" in h.chat.posts[-1].text


def test_feature_names_are_normalized_to_nfc(tmp_path):
    import unicodedata

    folder = tmp_path / "기능"
    folder.mkdir()
    (folder / (unicodedata.normalize("NFD", "가게씨 - 여행 지출과 정산") + ".md")).write_text("x")
    names = ProjectContext(repo=tmp_path, feature_dir=folder).feature_names()
    assert names == {"가게씨 - 여행 지출과 정산"}
    assert all(unicodedata.is_normalized("NFC", n) for n in names)
    assert ProjectContext(repo=tmp_path, feature_dir=tmp_path / "없음").feature_names() is None
