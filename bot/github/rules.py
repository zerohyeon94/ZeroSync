"""push 보호와 커밋 메시지 규칙 (운영 규약 4.4, 4.7). I/O 없이 단위 테스트로 고정한다."""

import re

from bot.schemas.design import BRANCH_NAME_PATTERN

COMMIT_TYPES = ("feat", "fix", "refactor", "test", "docs", "chore")
_SUBJECT = re.compile(
    r"^(feat|fix|refactor|test|docs|chore)(\([a-z][a-z0-9-]*\))?: (?P<text>\S.*)$"
)
# 의미 없는 요약 (운영 규약 4.4)
_MEANINGLESS = {"wip", "수정", "fix", "update", "변경", "작업", "커밋"}


class PushRefused(RuntimeError):
    """push 보호 조건을 만족하지 않는다."""


def check_push(branch: str, recorded: str | None) -> None:
    """두 조건을 모두 만족할 때만 push한다 (운영 규약 4.7).

    1. 이름이 `<feat|fix|refactor>/<Issue번호>-<slug>` 형식 (main, develop은 형식에서 빠진다)
    2. 이 작업에서 봇이 만들어 SQLite에 기록한 브랜치와 같은 이름
    """
    if not BRANCH_NAME_PATTERN.fullmatch(branch):
        raise PushRefused(f"브랜치 '{branch}'는 작업 브랜치 형식이 아니다")
    if recorded is None or branch != recorded:
        raise PushRefused(f"브랜치 '{branch}'는 이 작업에서 봇이 만든 브랜치가 아니다")


def commit_message_problems(message: str, issue_number: int) -> list[str]:
    """커밋 메시지가 운영 규약 4.4에 맞지 않는 이유. 맞으면 빈 목록."""
    lines = message.strip().splitlines()
    if not lines:
        return ["커밋 메시지가 비어 있다"]
    problems = []
    subject = lines[0].strip()
    match = _SUBJECT.match(subject)
    if match is None:
        problems.append(
            f"제목 '{subject}'가 '<type>(<영역>): <요약>' 형식이 아니다 "
            f"(type: {', '.join(COMMIT_TYPES)})"
        )
    elif match["text"].strip().lower() in _MEANINGLESS:
        problems.append(f"제목 '{subject}'의 요약이 의미 없는 말이다")
    if len(lines) > 1 and lines[1].strip():
        problems.append("제목과 본문 사이에 빈 줄이 있어야 한다")
    footer = f"Refs: #{issue_number}"
    if not any(line.strip() == footer for line in lines[1:]):
        problems.append(f"꼬리말 '{footer}'가 없다")
    return problems
