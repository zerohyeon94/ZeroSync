"""Codex CLI 러너 (SPEC 5.2).

`codex exec`를 read-only 샌드박스로 실행한다. Codex는 의견·토론·리뷰만 맡으므로 쓰기 모드는 없다.
- 프롬프트는 stdin으로 넘긴다 (`-` 인자)
- 마지막 메시지는 `-o <runs_dir>/<run_id>.last.txt`로 받아 응답 본문으로 쓴다.
  진행 기록은 stderr로 나와 실행 로그에만 남는다
- 응답 스키마는 `<runs_dir>/<run_id>.schema.json`에 써서 `--output-schema`로 넘긴다
- 세션 파일을 남기지 않고(`--ephemeral`), 사용자 설정(`~/.codex/config.toml`)은 읽지 않는다.
  로그인 정보는 그대로 쓴다
2026-10-10 시험 호출로 확인 (SPEC 10장 V2).
"""

import json
from collections.abc import Mapping
from pathlib import Path

from bot.agents.base import AgentName, AgentRequest, AgentResult, Stage
from bot.agents.process import ProcessRunner


class CodexCliRunner:
    name: AgentName = "codex"

    def __init__(
        self,
        process: ProcessRunner,
        executable: str = "codex",
        models: Mapping[Stage, str] | None = None,
    ):
        self._process = process
        self._executable = executable
        self._models = dict(models or {})

    def last_message_path(self, run_id: str) -> Path:
        return self._process.runs_dir / f"{run_id}.last.txt"

    def schema_path(self, run_id: str) -> Path:
        return self._process.runs_dir / f"{run_id}.schema.json"

    def build_argv(self, request: AgentRequest) -> list[str]:
        if request.mode != "read_only":
            raise ValueError("Codex는 읽기 전용 단계만 맡는다")
        argv = [
            self._executable,
            "exec",
            "--cd",
            str(request.cwd),
            "--sandbox",
            "read-only",
            "--ephemeral",
            "--ignore-user-config",
            "--color",
            "never",
            "--output-last-message",
            str(self.last_message_path(request.run_id)),
        ]
        if model := self._models.get(request.stage):
            argv += ["--model", model]
        if request.output_schema is not None:
            argv += ["--output-schema", str(self.schema_path(request.run_id))]
        argv.append("-")
        return argv

    async def run(self, request: AgentRequest) -> AgentResult:
        argv = self.build_argv(request)
        last_message = self.last_message_path(request.run_id)
        self._process.runs_dir.mkdir(parents=True, exist_ok=True)
        last_message.unlink(missing_ok=True)
        if request.output_schema is not None:
            self.schema_path(request.run_id).write_text(
                json.dumps(request.output_schema, ensure_ascii=False), encoding="utf-8"
            )

        result = await self._process.run(
            request.run_id,
            argv,
            cwd=request.cwd,
            timeout_sec=request.timeout_sec,
            stdin=request.prompt,
        )
        try:
            stdout = last_message.read_text(encoding="utf-8")
        except FileNotFoundError:
            stdout = result.stdout
        return AgentResult(
            status=result.status,
            exit_code=result.exit_code,
            stdout=stdout,
            stderr=result.stderr,
            session_id=None,
            duration_sec=result.duration_sec,
            log_path=result.log_path,
        )

    async def cancel(self, run_id: str) -> None:
        await self._process.cancel(run_id)
