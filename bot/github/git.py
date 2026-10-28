"""봇의 git 작업 (SPEC 6.2 GitOps, 운영 규약 4.3, 4.7).

셸 없이 인자 목록으로 git을 실행한다. 모든 push는 check_push를 통과해야 한다.
force push는 하지 않는다. 작업은 봇 전용 worktree에서 한다 (운영 규약 3.3).
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from bot.github.rules import check_push


class GitError(RuntimeError):
    pass


@dataclass(frozen=True)
class Commit:
    sha: str
    message: str


async def run_git(*args: str, cwd: Path) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args[:2])} 실패: {err.decode(errors='replace').strip()}")
    return out.decode(errors="replace")


class GitOps:
    async def prepare_worktree(self, repo: Path, path: Path, base_branch: str) -> None:
        """base 브랜치 최신 커밋에서 detached worktree를 만든다. 이미 있으면 그대로 쓴다."""
        if path.exists():
            return
        await run_git("fetch", "origin", base_branch, cwd=repo)
        path.parent.mkdir(parents=True, exist_ok=True)
        await run_git("worktree", "add", "--detach", str(path), f"origin/{base_branch}", cwd=repo)

    async def remove_worktree(self, repo: Path, path: Path) -> None:
        if path.exists():
            await run_git("worktree", "remove", "--force", str(path), cwd=repo)

    async def is_clean(self, path: Path) -> bool:
        return not (await run_git("status", "--porcelain", cwd=path)).strip()

    async def commits(self, path: Path, base_branch: str) -> list[Commit]:
        """base 브랜치 이후 이 worktree에 쌓인 커밋 (오래된 것부터)."""
        out = await run_git(
            "log", "--reverse", "--format=%H%x00%B%x1e", f"origin/{base_branch}..HEAD", cwd=path
        )
        commits = []
        for record in out.split("\x1e"):
            record = record.strip("\n")
            if record:
                sha, _, message = record.partition("\x00")
                commits.append(Commit(sha, message.strip()))
        return commits

    async def diff(self, path: Path, base_branch: str) -> str:
        return await run_git("diff", "--stat", "--patch", f"origin/{base_branch}...HEAD", cwd=path)

    async def current_branch(self, path: Path) -> str | None:
        name = (await run_git("branch", "--show-current", cwd=path)).strip()
        return name or None

    async def create_branch(self, path: Path, name: str) -> None:
        await run_git("switch", "-c", name, cwd=path)

    async def rename_branch(self, path: Path, old: str, new: str) -> None:
        await run_git("branch", "-m", old, new, cwd=path)

    async def push(self, path: Path, branch: str, *, recorded: str | None) -> None:
        check_push(branch, recorded)
        await run_git("push", "--set-upstream", "origin", f"{branch}:{branch}", cwd=path)

    async def delete_remote_branch(self, path: Path, branch: str, *, recorded: str | None) -> None:
        check_push(branch, recorded)
        await run_git("push", "origin", "--delete", branch, cwd=path)
