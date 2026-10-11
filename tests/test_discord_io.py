"""Discord 계층 테스트. 실제 Discord에는 연결하지 않는다 (SPEC 12.3).

규칙은 순수 함수로, DiscordChat은 가짜 웹훅으로, 봇의 입력 분기는 가짜 메시지·인터랙션으로 확인한다.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import discord
import pytest

from bot.config import load_config
from bot.discord_io.chat import DiscordChat
from bot.discord_io.client import EMPTY_POST, ZeroSyncBot
from bot.discord_io.rules import (
    AUTHOR_NAMES,
    IncomingMessage,
    MessageKind,
    classify,
    command_error,
    split_text,
)
from bot.render.status import render_ping, render_status
from bot.store.repo import TaskRecord
from bot.workflow.chat import Attachment
from bot.workflow.state import CommandName, TaskState

ZERO = 42
FORUM = 100
OPS = 300


def run(coro):
    return asyncio.run(coro)


# 규칙


def message(**overrides):
    data = {
        "message_id": 501,
        "author_id": ZERO,
        "from_bot": False,
        "channel_id": 500,
        "parent_id": FORUM,
    }
    data.update(overrides)
    return IncomingMessage(**data)


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, MessageKind.REPLY),
        ({"message_id": 500}, MessageKind.POST),  # 첫 메시지 ID == 스레드 ID
        ({"author_id": 7}, MessageKind.IGNORE),  # Zero가 아님
        ({"from_bot": True}, MessageKind.IGNORE),  # 봇·웹훅 (자기 게시 반복 방지)
        ({"parent_id": 999}, MessageKind.IGNORE),  # 등록되지 않은 포럼
        ({"parent_id": None}, MessageKind.IGNORE),  # 스레드가 아닌 채널
    ],
)
def test_classify(overrides, expected):
    assert classify(message(**overrides), zero_user_id=ZERO, forum_ids={FORUM}) is expected


def test_command_error():
    ok = {"zero_user_id": ZERO, "forum_ids": {FORUM}}
    assert command_error(user_id=ZERO, parent_id=FORUM, **ok) is None
    assert "Zero만" in command_error(user_id=7, parent_id=FORUM, **ok)
    assert "포럼의 게시글 안에서만" in command_error(user_id=ZERO, parent_id=None, **ok)
    assert "포럼의 게시글 안에서만" in command_error(user_id=ZERO, parent_id=999, **ok)


def test_split_text():
    assert split_text("짧다") == ["짧다"]
    assert split_text("") == [""]
    assert split_text("가" * 10, limit=4) == ["가가가가", "가가가가", "가가"]
    # 가능하면 줄바꿈에서 자른다
    assert split_text("aaa\nbbb\nccc", limit=8) == ["aaa\nbbb", "ccc"]
    chunks = split_text("x" * 5000)
    assert [len(c) for c in chunks] == [1900, 1900, 1200]
    with pytest.raises(ValueError):
        split_text("x", limit=0)


def test_author_names_follow_operating_rules():
    assert AUTHOR_NAMES == {
        "claude": "[Beta · Claude]",
        "codex": "[Alpha · Codex]",
        "bot": "[ZeroSync]",
    }


# DiscordChat


class FakeSender:
    def __init__(self):
        self.calls = []

    async def send(self, content=None, **kwargs):
        self.calls.append((content, kwargs))
        return SimpleNamespace(id=1000 + len(self.calls))


def make_chat():
    webhook, ops = FakeSender(), FakeSender()
    asked = []

    async def webhook_for(thread_id):
        asked.append(thread_id)
        return webhook

    async def ops_channel():
        return ops

    chat = DiscordChat(zero_user_id=ZERO, webhook_for=webhook_for, ops_channel=ops_channel)
    return chat, webhook, ops, asked


def test_post_silent_without_mention():
    chat, webhook, _, asked = make_chat()
    message_id = run(chat.post("500", "codex", "의견"))
    assert message_id == "1001"
    assert asked == [500]
    ((content, kwargs),) = webhook.calls
    assert content == "의견"
    assert kwargs["username"] == "[Alpha · Codex]"
    assert kwargs["thread"].id == 500
    assert kwargs["silent"] is True
    assert kwargs["wait"] is True
    assert kwargs["files"] == []
    assert kwargs["allowed_mentions"].users is False


def test_post_with_mention_splits_and_attaches_on_last():
    chat, webhook, _, _ = make_chat()
    text = "\n".join(["가" * 1000] * 3)
    message_id = run(
        chat.post("500", "claude", text, mention=True, attachments=[Attachment("a.md", "전문")])
    )
    assert message_id == "1001"
    assert len(webhook.calls) == 3
    first, middle, last = (kwargs for _, kwargs in webhook.calls)
    assert webhook.calls[0][0].startswith(f"<@{ZERO}>\n")
    assert [u.id for u in first["allowed_mentions"].users] == [ZERO]
    assert middle["allowed_mentions"].users is False  # 멘션은 첫 조각에만
    assert all(kwargs["silent"] is False for kwargs in (first, middle, last))
    assert first["files"] == [] and middle["files"] == []
    assert [f.filename for f in last["files"]] == ["a.md"]
    assert all(len(content) <= 1900 for content, _ in webhook.calls)


def test_notify_ops():
    chat, _, ops, _ = make_chat()
    run(chat.notify_ops("오류", mention=True))
    run(chat.notify_ops("시작"))
    (first, kwargs1), (second, kwargs2) = ops.calls
    assert first == f"<@{ZERO}>\n오류" and kwargs1["silent"] is False
    assert second == "시작" and kwargs2["silent"] is True


# /status, /ping 문구


def test_render_status_and_ping():
    task = TaskRecord(
        id=3,
        project="gagessi",
        discord_thread="500",
        title="예산 배너",
        state=TaskState.NEEDS_HUMAN,
        prev_state=TaskState.REVIEWING,
        review_round=2,
        test_retry=1,
        opinion_rounds=4,
        issue_number=None,
        pr_number=None,
        branch=None,
        worktree=None,
        claude_session=None,
        waiting_since=None,
        reminded_at=None,
        created_at="2026-10-10T09:00:00+00:00",
        updated_at="2026-10-10T09:00:00+00:00",
    )
    now = datetime(2026, 10, 10, 9, 0, tzinfo=UTC) + timedelta(hours=2, minutes=5)
    assert render_status(task, now) == (
        "작업 3 · 예산 배너\n상태: NEEDS_HUMAN\n직전 상태: REVIEWING\n질문 수: 4\n"
        "리뷰 라운드: 2\n테스트 재시도: 1\n마지막 변경 후: 2시간 5분"
    )
    assert render_ping(running_cli=1, active_tasks=2) == (
        "살아 있다. 실행 중 CLI 1개, 진행 중 작업 2개."
    )


# 봇 입력 분기


@pytest.fixture
def bot(tmp_path):
    projects = tmp_path / "projects.yaml"
    projects.write_text(
        "projects:\n"
        "  gagessi:\n"
        f'    forum_channel_id: "{FORUM}"\n'
        "    repo: /repo\n"
        "    github: owner/Gagessi\n"
        "    test: swift test\n"
        "    vault_dir: d\n    vault_hub: h.md\n    vault_tag: brain/g\n    vault_slug: g\n"
        "paths:\n  vault_projects: /vault\n",
        encoding="utf-8",
    )
    environ = {
        "DISCORD_TOKEN": "t",
        "DISCORD_GUILD_ID": "1",
        "ZERO_USER_ID": str(ZERO),
        "OPS_CHANNEL_ID": str(OPS),
    }
    config = load_config(projects, tmp_path / ".env", environ)
    tasks = {"500": object()}

    class Repo:
        async def find_task_by_thread(self, thread):
            return tasks.get(thread)

    instance = ZeroSyncBot(config, Repo(), {})
    calls = []

    class Engine:
        async def on_post(self, **kwargs):
            calls.append(("post", kwargs))

        async def on_message(self, thread, text, *, message_id=None):
            calls.append(("message", thread, text, message_id))

        async def on_command(self, thread, name, arg=""):
            calls.append(("command", thread, name, arg))

    instance.engine = Engine()
    instance.calls = calls
    return instance


def discord_message(*, message_id, channel_id=500, author_id=ZERO, content="질문", bot=False):
    channel = SimpleNamespace(id=channel_id, parent_id=FORUM, name="예산 배너")
    author = SimpleNamespace(id=author_id, bot=bot)
    return SimpleNamespace(
        id=message_id, channel=channel, author=author, content=content, webhook_id=None
    )


async def drain(bot):
    while bot._background:
        await asyncio.gather(*bot._background)


def test_forum_post_and_reply_reach_engine(bot):
    async def main():
        await bot.on_message(discord_message(message_id=500, content="  "))
        await bot.on_message(discord_message(message_id=501, content="추가 질문"))
        await bot.on_message(discord_message(message_id=502, author_id=7))
        await drain(bot)

    run(main())
    assert bot.calls == [
        ("post", {"project": "gagessi", "thread": "500", "title": "예산 배너", "text": EMPTY_POST}),
        ("message", "500", "추가 질문", "501"),
    ]


class FakeResponse:
    def __init__(self):
        self.sent = []

    async def send_message(self, content, **kwargs):
        self.sent.append((content, kwargs))


def interaction(user_id=ZERO, channel_id=500, parent_id=FORUM):
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id),
        channel=SimpleNamespace(parent_id=parent_id),
        channel_id=channel_id,
        response=FakeResponse(),
    )


def test_command_is_echoed_and_sent_to_engine(bot):
    async def main():
        it = interaction()
        await bot.run_command(it, CommandName.DECIDE, "배너로 간다")
        await drain(bot)
        return it

    it = run(main())
    assert it.response.sent == [("/decide 배너로 간다", {"silent": True})]
    assert bot.calls == [("command", "500", CommandName.DECIDE, "배너로 간다")]


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"user_id": 7}, "Zero만"),
        ({"parent_id": None}, "포럼의 게시글 안에서만"),
        ({"channel_id": 999}, "연결된 작업이 없다"),
    ],
)
def test_command_rejected_privately(bot, kwargs, expected):
    it = interaction(**kwargs)
    run(bot.run_command(it, CommandName.STOP))
    ((content, options),) = it.response.sent
    assert expected in content
    assert options == {"ephemeral": True}
    assert bot.calls == []


def test_background_error_is_reported_to_ops(bot, caplog):
    alerts = []

    async def notify_ops(text, *, mention=False):
        alerts.append((text, mention))

    bot.chat.notify_ops = notify_ops

    async def boom():
        raise RuntimeError("터짐")

    async def main():
        bot.spawn(boom(), "게시글 500")
        await drain(bot)

    run(main())
    assert alerts == [("게시글 500 처리 중 오류: RuntimeError: 터짐", True)]


def test_intents_include_message_content(bot):
    assert bot.intents.message_content is True
    assert isinstance(bot.guild_ref, discord.Object) and bot.guild_ref.id == 1
    names = {command.name for command in bot.tree.get_commands(guild=bot.guild_ref)}
    assert names == {"debate", "decide", "stop", "status", "ping"}


def test_startup_failure_alerts_ops_and_closes(bot):
    alerts, closed = [], []

    async def notify_ops(text, *, mention=False):
        alerts.append((text, mention))

    async def prepare():
        raise RuntimeError("gagessi의 forum_channel_id가 포럼 채널이 아니다 (#일반, 종류 text)")

    async def close():
        closed.append(True)

    bot.chat.notify_ops = notify_ops
    bot._prepare_webhooks = prepare
    bot.close = close
    run(bot.on_ready())

    assert closed == [True]
    assert isinstance(bot.startup_error, RuntimeError)
    ((text, mention),) = alerts
    assert "시작 실패" in text and "#일반" in text
    assert mention is True
