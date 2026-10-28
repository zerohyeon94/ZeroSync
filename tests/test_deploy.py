"""launchd 설정 템플릿 테스트 (SPEC 9.3)."""

import plistlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLIST = ROOT / "deploy" / "com.zerosync.orchestrator.plist"


def test_plist_template_runs_bot_from_repo_venv():
    text = PLIST.read_text(encoding="utf-8")
    data = plistlib.loads(
        text.replace("__REPO__", "/repo").replace("__HOME__", "/home/zero").encode("utf-8")
    )
    assert data["Label"] == "com.zerosync.orchestrator"
    assert data["ProgramArguments"] == [
        "/usr/bin/caffeinate", "-is", "/repo/.venv/bin/python", "-m", "bot"
    ]  # fmt: skip
    assert data["WorkingDirectory"] == "/repo"
    # launchd PATH에서도 Homebrew의 claude, codex, gh를 찾는다
    assert data["EnvironmentVariables"]["PATH"].startswith("/opt/homebrew/bin:")
    assert data["KeepAlive"] == {"SuccessfulExit": False}
    assert data["StandardErrorPath"] == "/home/zero/.zerosync/bot.err.log"


def test_install_script_is_executable():
    script = ROOT / "scripts" / "install_launchd.sh"
    assert script.stat().st_mode & 0o111
