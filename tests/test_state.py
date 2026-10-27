from dataclasses import dataclass

import pytest

from bot.workflow.state import (
    ALLOWED_COMMANDS,
    OPINION_NOTICE_AFTER,
    ApplyTypeLabel,
    CancelAgentRuns,
    CleanupStopped,
    ClearNeedsHuman,
    Command,
    CommandName,
    CreateIssue,
    FinishMerged,
    FixSource,
    Limits,
    MarkNeedsHuman,
    MarkReady,
    NoticeCode,
    PostCreated,
    PostNotice,
    PrMerged,
    PublishPr,
    RequestDebate,
    RequestOpinions,
    ReviewFinished,
    RunTests,
    StageFailed,
    StageSucceeded,
    StartDesign,
    StartFix,
    StartImplement,
    StartReview,
    TaskState,
    TestsFinished,
    WriteVaultDecision,
    ZeroMessage,
    start_task,
    transition,
)


@dataclass
class Task:
    state: TaskState = TaskState.OPINIONS
    opinion_rounds: int = 0
    prev_state: TaskState | None = None
    review_round: int = 0
    test_retry: int = 0
    review_limit_bonus: int = 0
    test_limit_bonus: int = 0
    recommended_fixed: int = 0


def notices(result, code):
    return [e for e in result.effects if isinstance(e, PostNotice) and e.code is code]


# 상태 분류


def test_terminal_and_waiting_states():
    assert {s for s in TaskState if s.is_terminal} == {TaskState.DONE, TaskState.STOPPED}
    assert {s for s in TaskState if s.waits_for_zero} == {
        TaskState.OPINIONS,
        TaskState.AWAIT_DESIGN_APPROVAL,
        TaskState.AWAIT_MERGE,
        TaskState.AWAIT_DOC_APPROVAL,
        TaskState.NEEDS_HUMAN,
    }


def test_allowed_commands_follow_spec_table():
    assert ALLOWED_COMMANDS[TaskState.OPINIONS] == {
        CommandName.DEBATE,
        CommandName.DECIDE,
        CommandName.STOP,
    }
    assert ALLOWED_COMMANDS[TaskState.AWAIT_DOC_APPROVAL] == {
        CommandName.APPROVE,
        CommandName.REVISE,
        CommandName.SKIP,
        CommandName.STOP,
    }
    assert ALLOWED_COMMANDS[TaskState.IMPLEMENTING] == {CommandName.STOP}
    assert ALLOWED_COMMANDS[TaskState.DONE] == set()
    assert ALLOWED_COMMANDS[TaskState.STOPPED] == set()


# 작업 생성


def test_post_starts_opinions_with_independent_first_opinions():
    result = start_task(PostCreated("예산 배너", "홈에 예산 초과 배너를 띄우자"))
    assert result.state is TaskState.OPINIONS
    assert result.effects == (
        RequestOpinions(("claude", "codex"), "홈에 예산 초과 배너를 띄우자", with_history=False),
    )
    assert result.updates == {"opinion_rounds": 0}


# OPINIONS


def test_message_asks_both_with_history_and_counts_question():
    result = transition(Task(opinion_rounds=2), ZeroMessage("  성능은 괜찮을까?  "))
    assert result.state is TaskState.OPINIONS
    assert result.effects == (
        RequestOpinions(("claude", "codex"), "성능은 괜찮을까?", with_history=True),
    )
    assert result.updates == {"opinion_rounds": 3}


@pytest.mark.parametrize(
    ("text", "agent", "question"),
    [
        ("@claude 설계 관점은?", "claude", "설계 관점은?"),
        ("@codex 반례는?", "codex", "반례는?"),
        ("  @Codex\n반례는?", "codex", "반례는?"),
        ("@claude", "claude", ""),
    ],
)
def test_mention_asks_only_that_agent(text, agent, question):
    result = transition(Task(), ZeroMessage(text))
    assert result.effects == (RequestOpinions((agent,), question, with_history=True),)
    assert result.updates == {"opinion_rounds": 1}


@pytest.mark.parametrize("text", ["@claudette 안녕", "질문 @claude", "@ codex 뭐"])
def test_text_that_is_not_a_leading_mention_goes_to_both(text):
    result = transition(Task(), ZeroMessage(text))
    assert result.effects[0].agents == ("claude", "codex")


def test_awaiting_decision_notice_once_when_questions_exceed_five():
    before = transition(Task(opinion_rounds=OPINION_NOTICE_AFTER - 1), ZeroMessage("질문"))
    crossing = transition(Task(opinion_rounds=OPINION_NOTICE_AFTER), ZeroMessage("질문"))
    after = transition(Task(opinion_rounds=OPINION_NOTICE_AFTER + 1), ZeroMessage("질문"))
    assert notices(before, NoticeCode.AWAITING_DECISION) == []
    assert len(notices(crossing, NoticeCode.AWAITING_DECISION)) == 1
    assert crossing.updates == {"opinion_rounds": OPINION_NOTICE_AFTER + 1}
    assert notices(after, NoticeCode.AWAITING_DECISION) == []


def test_debate_requests_rebuttal_without_counting_question():
    result = transition(Task(opinion_rounds=3), Command(CommandName.DEBATE))
    assert result.state is TaskState.OPINIONS
    assert result.effects == (RequestDebate(),)
    assert result.updates == {}


def test_decide_moves_to_designing_with_zero_original_text():
    result = transition(Task(), Command(CommandName.DECIDE, "  배너는 초과 시에만  "))
    assert result.state is TaskState.DESIGNING
    assert result.effects == (
        CreateIssue("배너는 초과 시에만"),
        WriteVaultDecision("배너는 초과 시에만"),
        StartDesign(),
    )


def test_decide_without_direction_is_rejected():
    result = transition(Task(), Command(CommandName.DECIDE, "   "))
    assert result.state is TaskState.OPINIONS
    [notice] = notices(result, NoticeCode.REJECTED)
    assert "/decide 뒤에 방향" in notice.detail


@pytest.mark.parametrize(
    "name", [CommandName.APPROVE, CommandName.REVISE, CommandName.SKIP, CommandName.FIX]
)
def test_commands_not_allowed_in_opinions_are_rejected_with_guidance(name):
    result = transition(Task(opinion_rounds=2), Command(name))
    assert result.state is TaskState.OPINIONS
    assert result.updates == {}
    [notice] = notices(result, NoticeCode.REJECTED)
    assert "OPINIONS" in notice.detail
    assert "/debate, /decide, /stop" in notice.detail


# /stop


@pytest.mark.parametrize("state", [s for s in TaskState if not s.is_terminal])
def test_stop_from_any_active_state(state):
    result = transition(Task(state=state), Command(CommandName.STOP))
    assert result.state is TaskState.STOPPED
    assert result.effects == (
        CancelAgentRuns(),
        CleanupStopped(),
        PostNotice(NoticeCode.STOPPED),
    )


@pytest.mark.parametrize("state", [TaskState.DONE, TaskState.STOPPED])
def test_terminal_states_reject_everything(state):
    for event in (Command(CommandName.STOP), ZeroMessage("다시"), Command(CommandName.DECIDE, "x")):
        result = transition(Task(state=state), event)
        assert result.state is state
        assert notices(result, NoticeCode.REJECTED)


# 아직 구현하지 않은 상태


def test_message_outside_opinions_is_rejected():
    result = transition(Task(state=TaskState.AWAIT_MERGE), ZeroMessage("언제 끝나?"))
    assert result.state is TaskState.AWAIT_MERGE
    [notice] = notices(result, NoticeCode.REJECTED)
    assert "/fix, /stop" in notice.detail


def test_doc_sync_commands_are_phase_3():
    with pytest.raises(NotImplementedError):
        transition(Task(state=TaskState.AWAIT_DOC_APPROVAL), Command(CommandName.APPROVE))


# Phase 2: 설계부터 merge까지


def step(state, event, **fields):
    return transition(Task(state=state, **fields), event, Limits())


def test_design_done_waits_for_approval_and_failure_needs_human():
    assert step(TaskState.DESIGNING, StageSucceeded()).state is TaskState.AWAIT_DESIGN_APPROVAL
    failed = step(TaskState.DESIGNING, StageFailed("형식 오류 반복"))
    assert failed.state is TaskState.NEEDS_HUMAN
    assert failed.effects == (MarkNeedsHuman("형식 오류 반복"),)
    assert failed.updates == {"prev_state": TaskState.DESIGNING}


def test_design_approval_commands():
    approved = step(TaskState.AWAIT_DESIGN_APPROVAL, Command(CommandName.APPROVE))
    assert approved.state is TaskState.IMPLEMENTING
    assert approved.effects == (ApplyTypeLabel(), StartImplement())

    revised = step(TaskState.AWAIT_DESIGN_APPROVAL, Command(CommandName.REVISE, " 배너 색 "))
    assert revised.state is TaskState.DESIGNING
    assert revised.effects == (StartDesign("배너 색"),)

    empty = step(TaskState.AWAIT_DESIGN_APPROVAL, Command(CommandName.REVISE, " "))
    assert empty.state is TaskState.AWAIT_DESIGN_APPROVAL
    assert "고칠 내용" in notices(empty, NoticeCode.REJECTED)[0].detail


@pytest.mark.parametrize("state", [TaskState.IMPLEMENTING, TaskState.FIXING])
def test_work_done_runs_tests(state):
    assert step(state, StageSucceeded()).effects == (RunTests(),)
    assert step(state, StageSucceeded()).state is TaskState.TESTING
    assert step(state, StageFailed("x")).updates == {"prev_state": state}


def test_tests_pass_opens_pr_and_review():
    result = step(TaskState.TESTING, TestsFinished(passed=True))
    assert result.state is TaskState.REVIEWING
    assert result.effects == (PublishPr(), StartReview())


def test_test_failures_fix_until_limit():
    first = step(TaskState.TESTING, TestsFinished(passed=False))
    assert first.state is TaskState.FIXING
    assert first.effects == (StartFix(FixSource.TESTS),)
    assert first.updates == {"test_retry": 1}
    # 2회 초과 시 NEEDS_HUMAN (Q2)
    assert step(TaskState.TESTING, TestsFinished(False), test_retry=1).state is TaskState.FIXING
    over = step(TaskState.TESTING, TestsFinished(False), test_retry=2)
    assert over.state is TaskState.NEEDS_HUMAN
    assert over.updates == {"prev_state": TaskState.TESTING, "test_retry": 3}


def test_environment_error_goes_to_needs_human_without_fix():
    result = step(
        TaskState.TESTING,
        TestsFinished(False, environment_error=True, detail="xcodebuild: error: no device"),
        test_retry=1,
    )
    assert result.state is TaskState.NEEDS_HUMAN
    assert result.effects == (MarkNeedsHuman("테스트 환경 오류: xcodebuild: error: no device"),)
    # 재시도 횟수는 그대로라 /resume하면 테스트만 다시 돈다
    assert result.updates == {"prev_state": TaskState.TESTING}
    resumed = step(
        TaskState.NEEDS_HUMAN,
        Command(CommandName.RESUME),
        prev_state=TaskState.TESTING,
        test_retry=1,
    )
    assert resumed.state is TaskState.TESTING
    assert resumed.effects[-1] == RunTests()


def test_review_rounds_until_limit():
    approved = step(TaskState.REVIEWING, ReviewFinished(approved=True))
    assert approved.state is TaskState.AWAIT_MERGE
    assert approved.effects == (MarkReady(),)

    changes = step(TaskState.REVIEWING, ReviewFinished(approved=False), review_round=2)
    assert changes.state is TaskState.FIXING
    assert changes.effects == (StartFix(FixSource.REVIEW),)
    assert changes.updates == {"review_round": 3}
    # 리뷰 3회 초과 시 NEEDS_HUMAN
    over = step(TaskState.REVIEWING, ReviewFinished(approved=False), review_round=3)
    assert over.state is TaskState.NEEDS_HUMAN
    assert over.updates["review_round"] == 4


def test_limits_include_resume_bonus():
    result = step(TaskState.REVIEWING, ReviewFinished(False), review_round=3, review_limit_bonus=1)
    assert result.state is TaskState.FIXING


def test_await_merge():
    merged = step(TaskState.AWAIT_MERGE, PrMerged())
    assert merged.state is TaskState.DONE
    assert merged.effects == (FinishMerged(),)

    fix = step(TaskState.AWAIT_MERGE, Command(CommandName.FIX, "권장 반영"))
    assert fix.state is TaskState.FIXING
    assert fix.effects == (StartFix(FixSource.RECOMMENDED),)
    assert fix.updates == {"recommended_fixed": 1}

    again = step(TaskState.AWAIT_MERGE, Command(CommandName.FIX), recommended_fixed=1)
    assert again.state is TaskState.AWAIT_MERGE
    assert "1회만" in notices(again, NoticeCode.REJECTED)[0].detail


@pytest.mark.parametrize(
    ("fields", "state", "effect", "updates"),
    [
        (
            {"prev_state": TaskState.TESTING, "test_retry": 3},
            TaskState.FIXING,
            StartFix(FixSource.TESTS),
            {"test_limit_bonus": 1},
        ),
        ({"prev_state": TaskState.TESTING, "test_retry": 1}, TaskState.TESTING, RunTests(), {}),
        (
            {"prev_state": TaskState.REVIEWING, "review_round": 4},
            TaskState.FIXING,
            StartFix(FixSource.REVIEW),
            {"review_limit_bonus": 1},
        ),
        ({"prev_state": TaskState.REVIEWING}, TaskState.REVIEWING, StartReview(), {}),
        ({"prev_state": TaskState.DESIGNING}, TaskState.DESIGNING, StartDesign(), {}),
        ({"prev_state": TaskState.IMPLEMENTING}, TaskState.IMPLEMENTING, StartImplement(), {}),
        ({"prev_state": TaskState.FIXING}, TaskState.FIXING, StartFix(FixSource.RESUME), {}),
    ],
)
def test_resume_from_needs_human(fields, state, effect, updates):
    result = step(TaskState.NEEDS_HUMAN, Command(CommandName.RESUME), **fields)
    assert result.state is state
    assert result.effects == (ClearNeedsHuman(), effect)
    # 카운터는 그대로 두고 한도만 늘린다 (Q4)
    assert dict(result.updates) == updates


def test_resume_without_resumable_prev_state_is_rejected():
    result = step(TaskState.NEEDS_HUMAN, Command(CommandName.RESUME), prev_state=None)
    assert result.state is TaskState.NEEDS_HUMAN
    assert notices(result, NoticeCode.REJECTED)


def test_late_internal_events_are_ignored():
    # /stop 뒤에 늦게 끝난 작업 결과는 상태를 바꾸지 않는다
    for event in (StageSucceeded(), TestsFinished(True), ReviewFinished(True), PrMerged()):
        result = step(TaskState.STOPPED, event)
        assert result.state is TaskState.STOPPED
    assert step(TaskState.AWAIT_DESIGN_APPROVAL, TestsFinished(True)).effects == ()
    assert step(TaskState.OPINIONS, StageSucceeded()).effects == ()
