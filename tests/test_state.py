from dataclasses import dataclass

import pytest

from bot.workflow.state import (
    ALLOWED_COMMANDS,
    OPINION_NOTICE_AFTER,
    CancelAgentRuns,
    Command,
    CommandName,
    CreateIssue,
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


@dataclass
class Task:
    state: TaskState = TaskState.OPINIONS
    opinion_rounds: int = 0


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
        StartDesign("배너는 초과 시에만"),
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
    assert result.effects == (CancelAgentRuns(), PostNotice(NoticeCode.STOPPED))


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


def test_allowed_but_unimplemented_command_raises():
    with pytest.raises(NotImplementedError):
        transition(Task(state=TaskState.AWAIT_DESIGN_APPROVAL), Command(CommandName.APPROVE))
