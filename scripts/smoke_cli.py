"""실제 claude·codex CLI를 짧게 불러 러너가 동작하는지 확인하는 수동 스크립트 (SPEC 12.3).

pytest에서는 실행하지 않는다. 구독 사용량이 조금 든다.
임시 git 저장소를 만들어 그 안에서만 실행하고, 끝나면 지운다.

    python scripts/smoke_cli.py                    # 둘 다 의견 + Claude 설계 단계 권한
    python scripts/smoke_cli.py --only claude --claude-model sonnet
"""

import argparse
import asyncio
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.agents import (  # noqa: E402
    AgentRequest,
    AgentResult,
    ClaudeCliRunner,
    CodexCliRunner,
    ProcessRunner,
    Stage,
)
from bot.schemas import AgentOutputError, Opinion, parse_agent_output  # noqa: E402

OPINION_PROMPT = (
    "이 저장소(메모 앱)에 다크 모드를 추가하자는 아이디어에 대한 의견을 "
    "주어진 스키마대로 짧게 작성해라."
)
DESIGN_PROMPT = (
    "다음을 시도하고 결과를 한 줄씩 보고해라. "
    "1) docs/설계/smoke.md 파일을 만들고 'ok'를 적어라. "
    "2) src/blocked.txt 파일을 만들고 'x'를 적어라. "
    "3) Bash로 'git push origin HEAD'를 실행해라."
)


def make_repo(base: Path) -> Path:
    repo = base / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# 메모 앱\n", encoding="utf-8")
    for args in (
        ["init", "-q"],
        ["add", "."],
        ["-c", "user.name=smoke", "-c", "user.email=smoke@localhost", "commit", "-qm", "init"],
    ):
        subprocess.run(["git", *args], cwd=repo, check=True)
    return repo


def request(repo: Path, stage: Stage, prompt: str, **kwargs) -> AgentRequest:
    return AgentRequest(
        run_id=f"smoke-{stage.value}-{uuid.uuid4().hex[:8]}",
        task_id=0,
        stage=stage,
        prompt=prompt,
        cwd=repo,
        timeout_sec=300,
        **kwargs,
    )


def report(label: str, result: AgentResult) -> bool:
    print(
        f"\n[{label}] status={result.status} exit={result.exit_code} "
        f"{result.duration_sec:.1f}s session={result.session_id}"
    )
    print(f"  log: {result.log_path}")
    try:
        opinion = parse_agent_output(result.stdout, Opinion)
    except AgentOutputError as error:
        print(f"  검증 실패: {error}")
        print(f"  원문: {result.stdout[:500]}")
        return False
    print(f"  {opinion.stance.label}: {opinion.conclusion}")
    return True


async def main(args: argparse.Namespace) -> int:
    ok = True
    with tempfile.TemporaryDirectory(prefix="zerosync-smoke-") as tmp:
        base = Path(tmp)
        repo = make_repo(base)
        process = ProcessRunner(base / "runs")
        schema = Opinion.model_json_schema()

        if args.only in (None, "claude"):
            models = {stage: args.claude_model for stage in Stage} if args.claude_model else {}
            claude = ClaudeCliRunner(process, args.claude, models)
            req = request(
                repo, Stage.OPINION, OPINION_PROMPT, mode="read_only", output_schema=schema
            )
            ok &= report("claude opinion", await claude.run(req))

            req = request(repo, Stage.DESIGN, DESIGN_PROMPT, mode="write_worktree")
            result = await claude.run(req)
            allowed = (repo / "docs" / "설계" / "smoke.md").exists()
            blocked = not (repo / "src" / "blocked.txt").exists()
            print(f"\n[claude design] status={result.status}")
            print(f"  docs/설계 쓰기 허용: {allowed}, src 쓰기 차단: {blocked}")
            print(f"  응답: {result.stdout[:500]}")
            ok &= allowed and blocked

        if args.only in (None, "codex"):
            models = {Stage.OPINION: args.codex_model} if args.codex_model else {}
            codex = CodexCliRunner(process, args.codex, models)
            req = request(
                repo, Stage.OPINION, OPINION_PROMPT, mode="read_only", output_schema=schema
            )
            ok &= report("codex opinion", await codex.run(req))

    print("\n결과:", "통과" if ok else "실패")
    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", choices=["claude", "codex"])
    parser.add_argument("--claude", default="claude", help="claude 실행 파일 경로")
    parser.add_argument("--codex", default="codex", help="codex 실행 파일 경로")
    parser.add_argument("--claude-model")
    parser.add_argument("--codex-model")
    raise SystemExit(asyncio.run(main(parser.parse_args())))
