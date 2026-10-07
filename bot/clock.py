"""현재 시각 (SPEC 7). 테스트에서는 FixedClock으로 고정한다.

저장 형식은 UTC ISO 8601 문자열이다 (SPEC 8).
"""

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    def __init__(self, at: datetime):
        if at.tzinfo is None:
            raise ValueError("시각에 시간대가 있어야 한다")
        self._now = at

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


def to_iso(at: datetime) -> str:
    if at.tzinfo is None:
        raise ValueError("시각에 시간대가 있어야 한다")
    return at.astimezone(UTC).isoformat()


def from_iso(text: str) -> datetime:
    return datetime.fromisoformat(text)
