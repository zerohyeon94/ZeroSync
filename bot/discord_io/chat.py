"""ChatIO의 Discord 구현 (SPEC 6.1).

- 모든 게시는 포럼 채널의 웹훅으로 보내고, 게시자 이름으로 주체를 구분한다 (운영 규약 1.2)
- 멘션은 Zero가 행동해야 할 때만 붙이고, 나머지는 알림 없는(silent) 메시지로 보낸다 (운영 규약 2.5)
- 긴 본문은 1,900자 단위로 나누고, 첨부 파일은 마지막 조각에 붙인다
"""

import io
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol

import discord

from bot.discord_io.rules import author_name, mention_text, split_text
from bot.org import DEFAULT_ORG, Org
from bot.workflow.chat import Attachment, Author


class WebhookLike(Protocol):
    async def send(self, content: str = ..., **kwargs: Any) -> Any: ...


class ChannelLike(Protocol):
    async def send(self, content: str | None = None, **kwargs: Any) -> Any: ...


class DiscordChat:
    def __init__(
        self,
        *,
        zero_user_id: int,
        webhook_for: Callable[[int], Awaitable[WebhookLike]],
        ops_channel: Callable[[], Awaitable[ChannelLike]],
        org: Org = DEFAULT_ORG,
    ):
        """webhook_for(thread_id)는 그 게시글이 속한 포럼 채널의 웹훅을 돌려준다."""
        self._zero = zero_user_id
        self._org = org
        self._webhook_for = webhook_for
        self._ops_channel = ops_channel

    def _mentions(self, mention: bool) -> discord.AllowedMentions:
        if mention:
            return discord.AllowedMentions(
                everyone=False, roles=False, users=[discord.Object(self._zero)]
            )
        return discord.AllowedMentions.none()

    def _content(self, text: str, mention: bool) -> list[str]:
        if mention:
            text = f"{mention_text(self._zero)}\n{text}"
        return split_text(text)

    async def post(
        self,
        thread: str,
        author: Author,
        text: str,
        *,
        mention: bool = False,
        attachments: Sequence[Attachment] = (),
    ) -> str:
        thread_id = int(thread)
        webhook = await self._webhook_for(thread_id)
        chunks = self._content(text, mention)
        first_id: str | None = None
        for index, chunk in enumerate(chunks):
            last = index == len(chunks) - 1
            files = [_file(a) for a in attachments] if last else []
            message = await webhook.send(
                chunk,
                username=author_name(self._org, author),
                thread=discord.Object(thread_id),
                allowed_mentions=self._mentions(mention and index == 0),
                silent=not mention,
                files=files,
                wait=True,
            )
            if first_id is None:
                first_id = str(message.id)
        assert first_id is not None
        return first_id

    async def notify_ops(self, text: str, *, mention: bool = False) -> None:
        channel = await self._ops_channel()
        for index, chunk in enumerate(self._content(text, mention)):
            await channel.send(
                chunk,
                allowed_mentions=self._mentions(mention and index == 0),
                silent=not mention,
            )


def _file(attachment: Attachment) -> discord.File:
    return discord.File(io.BytesIO(attachment.content.encode("utf-8")), attachment.filename)
