import subprocess
import sys

import pytest

from bot.locks import AlreadyRunningError, InstanceLock


def test_second_lock_fails_until_first_is_released(tmp_path):
    path = tmp_path / "nested" / "bot.lock"
    first = InstanceLock(path)
    first.acquire()
    assert first.held
    assert path.read_text().strip().isdigit()

    with pytest.raises(AlreadyRunningError, match="PID"):
        InstanceLock(path).acquire()

    first.release()
    assert not first.held
    with InstanceLock(path) as again:
        assert again.held


def test_lock_held_by_other_process(tmp_path):
    path = tmp_path / "bot.lock"
    code = (
        "import sys, time\n"
        "from pathlib import Path\n"
        "from bot.locks import InstanceLock\n"
        "lock = InstanceLock(Path(sys.argv[1])); lock.acquire()\n"
        "print('ready', flush=True); sys.stdin.read()\n"
    )
    holder = subprocess.Popen(
        [sys.executable, "-c", code, str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "ready"
        with pytest.raises(AlreadyRunningError, match=str(holder.pid)):
            InstanceLock(path).acquire()
    finally:
        # 락을 쥔 프로세스가 끝나면 운영체제가 락을 푼다
        holder.kill()
        holder.wait()
    with InstanceLock(path) as lock:
        assert lock.held


def test_acquire_twice_on_same_object_is_error(tmp_path):
    with InstanceLock(tmp_path / "bot.lock") as lock, pytest.raises(RuntimeError):
        lock.acquire()


def test_release_without_acquire_is_noop(tmp_path):
    InstanceLock(tmp_path / "bot.lock").release()
