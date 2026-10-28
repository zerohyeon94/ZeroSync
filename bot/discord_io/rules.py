"""Discord 입출력 규칙 (SPEC 4, 6.1). discord.py 객체 없이 판정해 단위 테스트로 고정한다."""

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum

from bot.org import Org
from bot.workflow.chat import Author


def author_name(org: Org, author: Author) -> str:
    """웹훅 게시 이름 `[이름 · 직책]` (운영 규약 1.2, SPEC Q16). 봇은 [ZeroSync]."""
    return f"[{org.display(author)}]"


WEBHOOK_NAME = "ZeroSync"
# Discord 메시지 최대 2,000자. 분할은 안전장치이고,
# 게시용 요약은 render가 1,500자로 맞춘다 (운영 규약 2.6)
SPLIT_LIMIT = 1900


class MessageKind(StrEnum):
    POST = "post"  # 포럼 게시글(스레드의 첫 메시지) → 작업 생성
    REPLY = "reply"  # 게시글 안의 일반 메시지 → 추가 질문
    IGNORE = "ignore"


@dataclass(frozen=True)
class IncomingMessage:
    message_id: int
    author_id: int
    from_bot: bool  # 봇 계정 또는 웹훅이 보낸 메시지
    channel_id: int
    parent_id: int | None  # 스레드면 부모 채널 ID


def classify(
    message: IncomingMessage, *, zero_user_id: int, forum_ids: Collection[int]
) -> MessageKind:
    """Zero가 프로젝트 포럼에 쓴 메시지만 처리한다. 그 밖의 입력은 무시한다 (SPEC 4)."""
    if message.from_bot or message.author_id != zero_user_id:
        return MessageKind.IGNORE
    if message.parent_id is None or message.parent_id not in forum_ids:
        return MessageKind.IGNORE
    # 포럼 게시글의 첫 메시지 ID는 스레드 ID와 같다
    if message.message_id == message.channel_id:
        return MessageKind.POST
    return MessageKind.REPLY


def command_error(
    *, user_id: int, zero_user_id: int, parent_id: int | None, forum_ids: Collection[int]
) -> str | None:
    """작업 명령을 쓸 수 없는 이유. 쓸 수 있으면 None."""
    if user_id != zero_user_id:
        return "이 봇의 명령은 Zero만 쓸 수 있다."
    if parent_id is None or parent_id not in forum_ids:
        return "이 명령은 프로젝트 포럼의 게시글 안에서만 쓸 수 있다."
    return None


def mention_text(zero_user_id: int) -> str:
    return f"<@{zero_user_id}>"


def split_text(text: str, limit: int = SPLIT_LIMIT) -> list[str]:
    """limit 이하 조각으로 나눈다. 가능하면 줄바꿈에서 자른다."""
    if limit <= 0:
        raise ValueError("limit은 1 이상이어야 한다")
    chunks: list[str] = []
    rest = text
    while len(rest) > limit:
        cut = rest.rfind("\n", 0, limit + 1)
        if cut <= 0:
            cut = limit
        chunks.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    if rest or not chunks:
        chunks.append(rest)
    return chunks
