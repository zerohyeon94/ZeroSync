"""단일 인스턴스 락 (SPEC 2.1).

같은 맥에서 봇은 하나만 실행한다. `flock`으로 잡으므로 프로세스가 비정상 종료돼도
운영체제가 락을 풀고, 남은 lock 파일을 지울 필요가 없다.
전역 빌드 락과 작업별 실행 락은 TESTING 단계와 함께 추가한다 (Phase 2).
"""

import fcntl
import os
from pathlib import Path
from types import TracebackType


class AlreadyRunningError(RuntimeError):
    """다른 봇 인스턴스가 락을 잡고 있다."""


class InstanceLock:
    def __init__(self, path: Path):
        self.path = path
        self._fd: int | None = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self) -> None:
        if self._fd is not None:
            raise RuntimeError("이미 락을 잡고 있다")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            holder = _read_pid(fd)
            os.close(fd)
            who = f" (PID {holder})" if holder else ""
            raise AlreadyRunningError(f"봇이 이미 실행 중이다{who}: {self.path}") from None
        except BaseException:
            os.close(fd)
            raise
        # 진단용으로 PID를 남긴다. 락 판정에는 쓰지 않는다
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        self._fd = fd

    def release(self) -> None:
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            os.ftruncate(fd, 0)
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def __enter__(self) -> "InstanceLock":
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()


def _read_pid(fd: int) -> str:
    try:
        text = os.pread(fd, 32, 0).decode(errors="replace").strip()
    except OSError:
        return ""
    return text if text.isdigit() else ""
