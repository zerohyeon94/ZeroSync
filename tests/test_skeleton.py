import subprocess
import sys

import bot
from bot.__main__ import main


def test_version_flag_prints_version(capsys):
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"zerosync {bot.__version__}"


def test_unknown_args_fail_with_message(capsys):
    assert main([]) == 1
    assert "--version" in capsys.readouterr().err


def test_importing_bot_does_not_load_discord_io():
    # 워크플로 계층은 Discord 계층 없이 import되어야 한다 (운영 규약 1.1-5)
    code = "import sys, bot; print('bot.discord_io' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "False"
