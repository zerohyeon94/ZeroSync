"""`python -m bot` 또는 `zerosync` 명령의 진입점."""

import sys

from bot import __version__


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args in (["--version"], ["-V"]):
        print(f"zerosync {__version__}")
        return 0
    print("ZeroSync 봇은 아직 골격만 있다. 실행 가능한 명령: --version", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
