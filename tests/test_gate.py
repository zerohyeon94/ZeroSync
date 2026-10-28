"""에이전트 실행 대기열 테스트 (SPEC 6.5, ADR-007)."""

import asyncio

import pytest

from bot.workflow.gate import AgentGate


def test_one_at_a_time_and_highest_priority_first():
    async def main():
        gate = AgentGate()
        order = []
        release = asyncio.Event()

        async def first():
            async with gate.slot((1, 0, 1)):
                order.append("first")
                await release.wait()

        async def job(name, priority):
            async with gate.slot(priority):
                order.append(name)

        running = asyncio.create_task(first())
        await asyncio.sleep(0)
        waiting = [
            asyncio.create_task(job("feature-orot", (1, 2, 5))),
            asyncio.create_task(job("feature-gagaessi", (1, 0, 9))),
            asyncio.create_task(job("chat", (0, 2, 7))),
        ]
        await asyncio.sleep(0)
        assert gate.waiting == 3 and order == ["first"]
        release.set()
        await asyncio.gather(running, *waiting)
        return order

    # Zero에게 바로 답하는 일 → 제품 순서 → 작업 번호
    assert asyncio.run(main()) == ["first", "chat", "feature-gagaessi", "feature-orot"]


def test_cancelled_waiter_does_not_block_others():
    async def main():
        gate = AgentGate()
        hold = asyncio.Event()

        async def holder():
            async with gate.slot((1,)):
                await hold.wait()

        async def waiter():
            async with gate.slot((1,)):
                return "ran"

        task = asyncio.create_task(holder())
        await asyncio.sleep(0)
        cancelled = asyncio.create_task(waiter())
        later = asyncio.create_task(waiter())
        await asyncio.sleep(0)
        cancelled.cancel()
        hold.set()
        await task
        result = await later
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        # 자리가 새지 않았다: 다시 바로 얻을 수 있다
        async with gate.slot((0,)):
            pass
        return result

    assert asyncio.run(main()) == "ran"


def test_concurrency_must_be_positive():
    with pytest.raises(ValueError):
        AgentGate(0)
