"""에이전트 실행 대기열 (SPEC 6.5, ADR-007).

에이전트 CLI는 한 번에 정해진 수(기본 1개)만 실행한다. 기다리는 실행은 우선순위가 높은 것부터
꺼낸다. 우선순위는 작은 튜플이 먼저다: (Zero가 방금 답한 일 여부, 제품 순서, 작업 번호).
테스트 명령은 이 대기열과 별개로 전역 락(TestRunner)이 하나씩 실행한다.
"""

import asyncio
import heapq
import itertools
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

Priority = tuple[int, ...]


class AgentGate:
    def __init__(self, concurrency: int = 1):
        if concurrency < 1:
            raise ValueError("동시 실행 수는 1 이상이어야 한다")
        self._free = concurrency
        self._waiters: list[tuple[Priority, int, asyncio.Future[None]]] = []
        self._seq = itertools.count()

    @property
    def waiting(self) -> int:
        """기다리는 실행 수 (/ping, 대시보드)."""
        return sum(1 for _, _, future in self._waiters if not future.done())

    @asynccontextmanager
    async def slot(self, priority: Priority) -> AsyncIterator[None]:
        await self._acquire(priority)
        try:
            yield
        finally:
            self._release()

    async def _acquire(self, priority: Priority) -> None:
        if self._free > 0 and not self.waiting:
            self._free -= 1
            return
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        heapq.heappush(self._waiters, (priority, next(self._seq), future))
        try:
            await future
        except asyncio.CancelledError:
            if future.done() and not future.cancelled():
                # 자리를 넘겨받은 직후 취소됐다. 받은 자리를 다음 차례에 돌려준다
                self._release()
            raise

    def _release(self) -> None:
        while self._waiters:
            _, _, future = heapq.heappop(self._waiters)
            if not future.done():
                future.set_result(None)  # 자리를 그대로 넘긴다
                return
        self._free += 1
