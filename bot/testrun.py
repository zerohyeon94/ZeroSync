"""테스트 실행 (SPEC 6.4, 운영 규약 1.7).

projects.yaml의 test 명령을 작업 worktree에서 셸 없이 실행한다. 빌드는 맥 자원을 많이 쓰므로
전역 락(동시 실행 수 limits.concurrent_builds) 아래에서 하나씩 돌린다.
결과는 종료 코드, 통과·실패 수, 실패 테스트명, 소요 시간으로 요약하고
전체 로그는 runs 폴더에 남긴다.
"""

import asyncio
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from bot.agents.base import RunStatus
from bot.agents.process import ProcessRunner

MAX_FAILED_TESTS = 10
MAX_ERRORS = 5

# XCTest: "Executed 12 tests, with 1 failure (0 unexpected) in 0.5 (0.6) seconds"
_XCTEST_SUMMARY = re.compile(r"Executed (\d+) tests?, with (\d+) failures?")
_XCTEST_FAILED = re.compile(r"Test Case '-\[(?P<name>[^\]]+)\]' failed")
# Swift Testing: "✘ Test run with 10 tests in 2 suites failed after 0.1 seconds with 2 issues."
_SWIFT_RUN = re.compile(r"Test run with (\d+) tests?(?: in \d+ suites?)? (passed|failed)")
_SWIFT_ISSUES = re.compile(r"with (\d+) issues?")
_SWIFT_FAILED = re.compile(r"✘ Test (?!run with)(?P<name>.+?) (?:failed|recorded an issue)")
_ERROR_LINE = re.compile(r"(^|\s)error: ")


@dataclass(frozen=True)
class TestReport:
    __test__ = False  # pytest가 테스트 클래스로 모으지 않게
    status: RunStatus  # 프로세스 결과 (ok는 종료 코드 0)
    exit_code: int | None
    total: int | None
    failures: int | None
    failed_tests: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)  # 빌드 오류 등
    duration_sec: float = 0.0
    log_path: str = ""

    @property
    def passed(self) -> bool:
        return self.status is RunStatus.OK and not self.failures

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TestReport":
        names = {name for name in cls.__dataclass_fields__}
        data = {key: value for key, value in payload.items() if key in names}
        data["status"] = RunStatus(data["status"])
        return cls(**data)

    def to_payload(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["passed"] = self.passed
        return data


def summarize(output: str) -> tuple[int | None, int | None, list[str], list[str]]:
    """테스트 출력에서 (전체 수, 실패 수, 실패 테스트명, 오류 줄)을 뽑는다."""
    total = failures = None
    xctest = _XCTEST_SUMMARY.findall(output)
    if xctest:
        # 마지막 줄이 전체 합계다
        total, failures = int(xctest[-1][0]), int(xctest[-1][1])
    swift = _SWIFT_RUN.findall(output)
    if swift:
        swift_total = int(swift[-1][0])
        issues = _SWIFT_ISSUES.findall(output.split("Test run with")[-1])
        swift_failures = int(issues[0]) if swift[-1][1] == "failed" and issues else 0
        total = (total or 0) + swift_total
        failures = (failures or 0) + swift_failures
    failed: list[str] = []
    for pattern in (_XCTEST_FAILED, _SWIFT_FAILED):
        for match in pattern.finditer(output):
            name = match["name"].strip()
            if name not in failed:
                failed.append(name)
    errors = []
    for line in output.splitlines():
        if _ERROR_LINE.search(line) and line.strip() not in errors:
            errors.append(line.strip()[:300])
    return total, failures, failed[:MAX_FAILED_TESTS], errors[:MAX_ERRORS]


class TestRunner:
    __test__ = False

    def __init__(self, process: ProcessRunner, *, concurrent: int = 1, timeout_sec: float = 3600):
        self._process = process
        self._lock = asyncio.Semaphore(concurrent)
        self._timeout = timeout_sec

    async def run(self, run_id: str, argv: Sequence[str], *, cwd: Path) -> TestReport:
        async with self._lock:
            result = await self._process.run(run_id, argv, cwd=cwd, timeout_sec=self._timeout)
        total, failures, failed, errors = summarize(result.stdout + "\n" + result.stderr)
        if result.status is RunStatus.OK and failures is None:
            failures = 0
        if result.status is not RunStatus.OK and not failures and not failed and not errors:
            errors = [f"테스트 명령이 실패했다 (종료 코드 {result.exit_code}, {result.status})"]
        return TestReport(
            status=result.status,
            exit_code=result.exit_code,
            total=total,
            failures=failures,
            failed_tests=failed,
            errors=errors,
            duration_sec=round(result.duration_sec, 1),
            log_path=str(result.log_path),
        )

    async def cancel(self, run_id: str) -> None:
        await self._process.cancel(run_id)
