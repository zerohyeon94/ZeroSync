import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

from bot.agents import (
    AgentRequest,
    AgentResult,
    FakeAgentRunner,
    ProcessRunner,
    RunStatus,
    Stage,
)

PY = sys.executable


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def runner(tmp_path):
    return ProcessRunner(tmp_path / "runs", terminate_grace_sec=1.0)


def py(code: str) -> list[str]:
    return [PY, "-c", code]


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def wait_until_dead(pid: int, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return True
        time.sleep(0.05)
    return False


# ProcessRunner


def test_ok_run_collects_output_and_writes_log(runner, tmp_path):
    code = "import sys; print('안녕'); print('경고', file=sys.stderr)"
    result = run(runner.run("r1", py(code), cwd=tmp_path, timeout_sec=10))
    assert result.status is RunStatus.OK
    assert result.exit_code == 0
    assert result.stdout == "안녕\n"
    assert result.stderr == "경고\n"
    assert result.log_path == tmp_path / "runs" / "r1.log"
    log = result.log_path.read_text(encoding="utf-8")
    assert "status: ok" in log
    assert "안녕" in log and "경고" in log


def test_nonzero_exit_is_error(runner, tmp_path):
    result = run(runner.run("r1", py("import sys; sys.exit(3)"), cwd=tmp_path, timeout_sec=10))
    assert result.status is RunStatus.ERROR
    assert result.exit_code == 3


def test_missing_executable_is_error(runner, tmp_path):
    result = run(runner.run("r1", ["/없는/명령"], cwd=tmp_path, timeout_sec=10))
    assert result.status is RunStatus.ERROR
    assert result.exit_code is None
    assert "시작하지 못했다" in result.stderr
    assert result.log_path.exists()


def test_arguments_are_not_interpreted_by_shell(runner, tmp_path):
    tricky = "$(echo 주입); rm -rf ~ && `id` | cat > x \"'"
    code = "import sys; sys.stdout.write(sys.argv[1])"
    result = run(runner.run("r1", [PY, "-c", code, tricky], cwd=tmp_path, timeout_sec=10))
    assert result.stdout == tricky
    assert not (tmp_path / "x").exists()


def test_stdin_and_cwd(runner, tmp_path):
    code = "import os, sys; print(os.getcwd()); print(sys.stdin.read().upper())"
    result = run(runner.run("r1", py(code), cwd=tmp_path, timeout_sec=10, stdin="prompt"))
    cwd_line, stdin_line = result.stdout.splitlines()
    assert Path(cwd_line).resolve() == tmp_path.resolve()
    assert stdin_line == "PROMPT"


def test_timeout_kills_process_group(runner, tmp_path):
    # 자식이 손자 프로세스를 띄운 상태에서 타임아웃 -> 손자까지 종료되어야 한다
    pid_file = tmp_path / "grandchild.pid"
    code = (
        "import subprocess, sys, time\n"
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(p.pid))\n"
        "print('started', flush=True)\n"
        "time.sleep(60)\n"
    )
    result = run(runner.run("r1", py(code), cwd=tmp_path, timeout_sec=1.0))
    assert result.status is RunStatus.TIMEOUT
    assert "started" in result.stdout  # 타임아웃 전까지의 출력은 남는다
    assert wait_until_dead(int(pid_file.read_text()))


def test_cancel_by_run_id(runner, tmp_path):
    async def scenario():
        task = asyncio.create_task(
            runner.run("r1", py("import time; time.sleep(60)"), cwd=tmp_path, timeout_sec=30)
        )
        while not runner.is_running("r1"):
            await asyncio.sleep(0.01)
        await runner.cancel("r1")
        return await task

    result = run(scenario())
    assert result.status is RunStatus.CANCELLED
    assert not runner.is_running("r1")


def test_cancel_unknown_run_id_is_noop(runner):
    run(runner.cancel("없음"))


def test_cancelling_the_task_terminates_process(runner, tmp_path):
    pid_file = tmp_path / "child.pid"
    code = f"import os, time; open({str(pid_file)!r}, 'w').write(str(os.getpid())); time.sleep(60)"

    async def scenario():
        task = asyncio.create_task(runner.run("r1", py(code), cwd=tmp_path, timeout_sec=30))
        while not pid_file.exists() or not pid_file.read_text():
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    run(scenario())
    assert wait_until_dead(int(pid_file.read_text()))
    assert not runner.is_running("r1")


def test_duplicate_run_id_is_rejected(runner, tmp_path):
    async def scenario():
        task = asyncio.create_task(
            runner.run("r1", py("import time; time.sleep(60)"), cwd=tmp_path, timeout_sec=30)
        )
        while not runner.is_running("r1"):
            await asyncio.sleep(0.01)
        with pytest.raises(ValueError, match="이미 실행 중"):
            await runner.run("r1", py("pass"), cwd=tmp_path, timeout_sec=5)
        await runner.cancel("r1")
        await task

    run(scenario())


def test_event_loop_stays_responsive_while_process_runs(runner, tmp_path):
    # 자식 프로세스 실행 중에도 다른 작업(/status, /stop 응답)이 진행되어야 한다 (SPEC 2.1)
    async def scenario():
        task = asyncio.create_task(
            runner.run("r1", py("import time; time.sleep(1)"), cwd=tmp_path, timeout_sec=10)
        )
        ticks = 0
        while not task.done():
            ticks += 1
            await asyncio.sleep(0.05)
        return ticks, await task

    ticks, result = run(scenario())
    assert result.status is RunStatus.OK
    assert ticks >= 5


# FakeAgentRunner


def request(run_id="r1", stage=Stage.OPINION):
    return AgentRequest(
        run_id=run_id,
        task_id=1,
        stage=stage,
        prompt="의견을 달라",
        cwd=Path("."),
        mode="read_only",
        timeout_sec=60,
    )


def test_fake_runner_returns_responses_in_order_and_records_requests():
    fake = FakeAgentRunner("claude", ["첫 응답", lambda req: f"{req.stage} 응답"])
    first = run(fake.run(request("r1")))
    second = run(fake.run(request("r2", Stage.REVIEW)))
    assert first.status is RunStatus.OK and first.stdout == "첫 응답"
    assert second.stdout == "review 응답"
    assert [r.run_id for r in fake.requests] == ["r1", "r2"]


def test_fake_runner_can_return_full_result_and_record_cancel(tmp_path):
    timeout = AgentResult(RunStatus.TIMEOUT, None, "", "", None, 3600.0, tmp_path / "r1.log")
    fake = FakeAgentRunner("codex", [timeout])
    assert run(fake.run(request())).status is RunStatus.TIMEOUT
    run(fake.cancel("r1"))
    assert fake.cancelled == ["r1"]


def test_fake_runner_fails_when_responses_run_out():
    fake = FakeAgentRunner("claude")
    with pytest.raises(AssertionError, match="준비된 응답이 없다"):
        run(fake.run(request()))
