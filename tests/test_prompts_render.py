"""프롬프트 스냅샷, 렌더링, 멘션 규칙 테스트.

스냅샷을 의도적으로 바꿨다면 `UPDATE_SNAPSHOTS=1 pytest tests/test_prompts_render.py`로 갱신한다.
"""

import os
from pathlib import Path

import pytest

from bot.prompts import HistoryEntry, debate_prompt, opinion_prompt, with_format_error
from bot.render import MAX_POST_LENGTH, render_format_error, render_notice, render_opinion_post
from bot.schemas import Opinion
from bot.workflow.mentions import ACTION_REQUIRED, Moment, should_mention
from bot.workflow.state import NoticeCode

SNAPSHOTS = Path(__file__).parent / "snapshots"


def check_snapshot(name: str, text: str) -> None:
    path = SNAPSHOTS / f"{name}.txt"
    if os.environ.get("UPDATE_SNAPSHOTS") == "1" or not path.exists():
        path.write_text(text, encoding="utf-8")
    assert text == path.read_text(encoding="utf-8")


def make_opinion(**overrides):
    data = {
        "stance": "conditional",
        "conclusion": "배너는 좋지만 끌 수 있어야 한다",
        "reasons": ["초과 사실을 바로 알 수 있다", "기존 알림 설정을 재사용할 수 있다"],
        "risks": ["배너가 반복되면 피로하다"],
        "proposal": "하루 한 번만 띄우고 설정에서 끌 수 있게 한다",
    }
    data.update(overrides)
    return Opinion.model_validate(data)


HISTORY = [
    HistoryEntry("claude", "**찬성** — 배너로 충분하다"),
    HistoryEntry("codex", "**반대** — 푸시 알림이 더 단순하다"),
    HistoryEntry("zero", "@codex 푸시 권한이 없으면?"),
]


# 프롬프트


def test_first_opinion_prompt_snapshot():
    prompt = opinion_prompt(
        "claude", title="예산 배너", post="예산을 넘으면 배너를 띄우자\n가능할까?"
    )
    assert "지금까지의 흐름" not in prompt
    for name in ("persona", "perspective", "title", "post", "history", "request", "schema"):
        assert f"${name}" not in prompt
    check_snapshot("opinion_first_claude", prompt)


def test_follow_up_prompt_snapshot():
    prompt = opinion_prompt(
        "codex",
        title="예산 배너",
        post="예산을 넘으면 배너를 띄우자",
        question="푸시 권한이 없으면?",
        history=HISTORY,
    )
    assert "[Alpha · Codex]" in prompt and "[Zero]" in prompt
    check_snapshot("opinion_follow_up_codex", prompt)


def test_debate_prompt_snapshot():
    prompt = debate_prompt(
        "claude",
        title="예산 배너",
        post="예산을 넘으면 배너를 띄우자",
        own="**찬성** — 배너로 충분하다",
        other_agent="codex",
        other="**반대** — 푸시 알림이 더 단순하다",
        history=HISTORY,
    )
    check_snapshot("debate_claude", prompt)


def test_personas_differ_by_agent():
    beta = opinion_prompt("claude", title="t", post="p")
    alpha = opinion_prompt("codex", title="t", post="p")
    assert "Beta · Claude (ISFJ)" in beta and "장기 유지보수" in beta
    assert "Alpha · Codex (INTJ)" in alpha and "엣지 케이스" in alpha


def test_post_text_with_dollar_sign_is_kept():
    assert "가격 $5 이상" in opinion_prompt("claude", title="t", post="가격 $5 이상")


def test_format_error_prompt_appends_error():
    retried = with_format_error("원래 프롬프트\n", "스키마 검증 실패:\n- risks: 최소 1개")
    assert retried.startswith("원래 프롬프트\n\n## 이전 출력의 형식 오류")
    assert "- risks: 최소 1개" in retried


# 렌더링


def test_render_opinion_post():
    post = render_opinion_post(make_opinion())
    assert post.attachments == ()
    assert post.text == (
        "**조건부 찬성** — 배너는 좋지만 끌 수 있어야 한다\n\n"
        "근거\n- 초과 사실을 바로 알 수 있다\n- 기존 알림 설정을 재사용할 수 있다\n\n"
        "위험\n- 배너가 반복되면 피로하다\n\n"
        "제안\n하루 한 번만 띄우고 설정에서 끌 수 있게 한다"
    )
    assert render_opinion_post(make_opinion(), heading="반박").text.startswith(
        "반박 · **조건부 찬성**"
    )


def test_long_opinion_is_attached():
    long = make_opinion(reasons=["가" * 200] * 4, risks=["나" * 200] * 3, proposal="다" * 300)
    post = render_opinion_post(long)
    assert len(post.text) <= MAX_POST_LENGTH
    assert "첨부 파일" in post.text
    (attachment,) = post.attachments
    assert attachment.filename == "opinion.md"
    assert "다" * 300 in attachment.content


def test_render_format_error():
    short = render_format_error("그냥 문장", "```json 코드 블록을 찾지 못했다\n추가")
    assert short.text.startswith("**형식 오류** — 출력이 의견 형식에 맞지 않았다 (```json")
    assert "```\n그냥 문장\n```" in short.text
    long = render_format_error("x" * 1000, "오류")
    assert long.attachments[0].content == "x" * 1000
    fenced = render_format_error("```json\n{}\n```", "오류")
    assert fenced.attachments
    assert "비어 있었다" in render_format_error("  ", "오류").text


def test_every_notice_code_has_text():
    for code in NoticeCode:
        assert render_notice(code)
    assert render_notice(NoticeCode.REJECTED, "현재 상태: X") == "현재 상태: X"
    assert render_notice(NoticeCode.AGENT_FAILED, "[Alpha · Codex] timeout").endswith(
        "\n[Alpha · Codex] timeout"
    )


# 멘션 규칙 (운영 규약 2.5)


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (Moment.OPINIONS_READY, True),
        (Moment.DESIGN_READY, True),
        (Moment.FINAL_APPROVAL, True),
        (Moment.DOC_SYNC_READY, True),
        (Moment.NEEDS_HUMAN, True),
        (Moment.BOT_ERROR, True),
        (Moment.IMPLEMENT_STARTED, False),
        (Moment.TEST_RUNNING, False),
        (Moment.REVIEW_RUNNING, False),
        (Moment.TEST_RESULT, False),
        (Moment.REVIEW_ROUND_RESULT, False),
        (Moment.NOTICE, False),
    ],
)
def test_mention_rules(moment, expected):
    assert should_mention(moment) is expected


def test_action_required_covers_only_listed_moments():
    assert len(ACTION_REQUIRED) == 6
    assert set(Moment) - ACTION_REQUIRED == {
        Moment.IMPLEMENT_STARTED,
        Moment.TEST_RUNNING,
        Moment.REVIEW_RUNNING,
        Moment.TEST_RESULT,
        Moment.REVIEW_ROUND_RESULT,
        Moment.NOTICE,
    }
