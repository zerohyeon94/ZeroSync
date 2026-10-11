import asyncio
import sys

from bot.agents import ProcessRunner, RunStatus
from bot.testrun import TestRunner, summarize

XCTEST_PASS = """\
Test Suite 'All tests' started at 2026-10-11 10:00:00.000.
Test Case '-[GagaeSsiTests.BudgetTests testUnder]' passed (0.001 seconds).
Executed 3 tests, with 0 failures (0 unexpected) in 0.010 (0.012) seconds
Executed 12 tests, with 0 failures (0 unexpected) in 0.050 (0.060) seconds
** TEST SUCCEEDED **
"""

XCTEST_FAIL = """\
Test Case '-[GagaeSsiTests.BudgetTests testOver]' failed (0.002 seconds).
/x/BudgetTests.swift:20: error: -[GagaeSsiTests.BudgetTests testOver] : XCTAssertEqual failed
Test Case '-[GagaeSsiTests.TripTests testEnd]' failed (0.001 seconds).
Executed 12 tests, with 2 failures (0 unexpected) in 0.050 (0.060) seconds
** TEST FAILED **
"""

SWIFT_TESTING_FAIL = """\
✘ Test budgetOver() recorded an issue at BudgetTests.swift:10:5: Expectation failed
✘ Test budgetOver() failed after 0.001 seconds with 1 issue.
✘ Test run with 5 tests in 2 suites failed after 0.010 seconds with 1 issue.
"""

BUILD_FAIL = """\
/x/HomeView.swift:42:13: error: cannot find 'bannerView' in scope
** TEST FAILED **
"""


def test_summarize_xctest():
    assert summarize(XCTEST_PASS) == (12, 0, [], [])
    total, failures, failed, errors = summarize(XCTEST_FAIL)
    assert (total, failures) == (12, 2)
    assert failed == ["GagaeSsiTests.BudgetTests testOver", "GagaeSsiTests.TripTests testEnd"]
    assert len(errors) == 1


def test_summarize_swift_testing_and_build_errors():
    total, failures, failed, _ = summarize(SWIFT_TESTING_FAIL)
    assert (total, failures) == (5, 1)
    assert failed == ["budgetOver()"]
    total, failures, failed, errors = summarize(BUILD_FAIL)
    assert (total, failures, failed) == (None, None, [])
    assert errors == ["/x/HomeView.swift:42:13: error: cannot find 'bannerView' in scope"]


def run_tests(tmp_path, script, *, concurrent=1):
    runner = TestRunner(ProcessRunner(tmp_path / "runs"), concurrent=concurrent, timeout_sec=10)
    argv = [sys.executable, "-c", script]
    return runner, argv


def test_runner_reports_pass_and_fail(tmp_path):
    runner, ok = run_tests(tmp_path, f"print({XCTEST_PASS!r})")
    report = asyncio.run(runner.run("t1", ok, cwd=tmp_path))
    assert report.passed and report.total == 12 and report.failures == 0
    assert report.to_payload()["passed"] is True
    assert (tmp_path / "runs" / "t1.log").exists()

    _, failing = run_tests(tmp_path, f"print({XCTEST_FAIL!r}); raise SystemExit(65)")
    report = asyncio.run(runner.run("t2", failing, cwd=tmp_path))
    assert not report.passed
    assert report.status is RunStatus.ERROR and report.exit_code == 65
    assert report.failures == 2

    _, crash = run_tests(tmp_path, "raise SystemExit(70)")
    report = asyncio.run(runner.run("t3", crash, cwd=tmp_path))
    assert not report.passed
    assert "종료 코드 70" in report.errors[0]


def test_runner_holds_global_lock(tmp_path):
    """동시 실행 수 1이면 두 테스트가 겹치지 않는다."""
    marker = tmp_path / "running"
    script = (
        "import pathlib, sys, time\n"
        f"m = pathlib.Path({str(marker)!r})\n"
        "if m.exists(): sys.exit(9)\n"
        "m.write_text('x'); time.sleep(0.3); m.unlink()\n"
        "print('Executed 1 test, with 0 failures')\n"
    )
    runner, argv = run_tests(tmp_path, script)

    async def both():
        return await asyncio.gather(
            runner.run("a", argv, cwd=tmp_path), runner.run("b", argv, cwd=tmp_path)
        )

    first, second = asyncio.run(both())
    assert first.passed and second.passed
