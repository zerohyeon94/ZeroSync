"""`python -m bot` 또는 `zerosync` 명령의 진입점.

지금은 설정을 읽고 단일 인스턴스 락을 잡는 데까지만 한다. Discord 연결과 이벤트 루프는
`feat/0-discord-opinions`에서 붙인다 (SPEC 12.2).
"""

import sys
from collections.abc import Mapping
from pathlib import Path

from bot import __version__
from bot.config import DEFAULT_ENV_PATH, DEFAULT_PROJECTS_PATH, ConfigError, load_config
from bot.locks import AlreadyRunningError, InstanceLock


def main(
    argv: list[str] | None = None,
    *,
    projects_path: Path = DEFAULT_PROJECTS_PATH,
    env_path: Path = DEFAULT_ENV_PATH,
    environ: Mapping[str, str] | None = None,
) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args in (["--version"], ["-V"]):
        print(f"zerosync {__version__}")
        return 0
    if args:
        print("사용법: zerosync [--version]", file=sys.stderr)
        return 2

    try:
        config = load_config(projects_path, env_path, environ)
    except ConfigError as error:
        print(f"설정 오류: {error}", file=sys.stderr)
        return 1
    try:
        with InstanceLock(config.paths.lock):
            print(f"설정 확인: 프로젝트 {', '.join(config.projects)}", file=sys.stderr)
            print("Discord 연결은 아직 구현되지 않았다. 종료한다", file=sys.stderr)
    except AlreadyRunningError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
