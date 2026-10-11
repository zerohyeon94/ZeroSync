"""대시보드 HTTP 서버 (표준 라이브러리).

127.0.0.1에만 연결한다. 실행 로그에는 프롬프트와 앱 코드 내용이 들어 있어 이 맥 밖으로 열지 않는다.
실행 로그는 설정의 runs 폴더 안에 있는 파일만 보여 준다.
"""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from bot.dashboard import queries, views
from bot.workflow.state import TaskState

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
RUN_LIMIT = 200


@dataclass(frozen=True)
class DashboardSettings:
    db: Path
    runs_dir: Path
    guild_id: str | None = None  # 있으면 작업에 Discord 게시글 링크를 단다

    def discord_url(self, thread: str) -> str | None:
        if not self.guild_id:
            return None
        return f"https://discord.com/channels/{self.guild_id}/{thread}"


@dataclass(frozen=True)
class Response:
    status: HTTPStatus
    body: str
    content_type: str = "text/html; charset=utf-8"


def handle(settings: DashboardSettings, path: str) -> Response:
    """요청 경로 하나를 처리한다. 서버와 분리해 테스트에서 바로 부른다."""
    url = urlsplit(path)
    params = {key: values[0] for key, values in parse_qs(url.query).items()}
    parts = [unquote(part) for part in url.path.strip("/").split("/") if part]
    try:
        conn = queries.open_readonly(settings.db)
    except queries.DatabaseMissing as error:
        return Response(HTTPStatus.OK, views.message_page("기록 없음", str(error)))
    try:
        return _route(settings, conn, parts, params)
    finally:
        conn.close()


def _route(
    settings: DashboardSettings,
    conn: sqlite3.Connection,
    parts: list[str],
    params: dict[str, str],
) -> Response:
    if not parts:
        return _ok(views.summary_page(queries.project_summaries(conn), queries.stage_stats(conn)))
    if parts == ["tasks"]:
        project, state = params.get("project", ""), params.get("state", "")
        tasks = queries.list_tasks(conn, project=project or None, state=state or None)
        return _ok(
            views.tasks_page(
                tasks,
                projects=queries.projects(conn),
                states=[s.value for s in TaskState],
                project=project,
                state=state,
                discord_url=settings.discord_url,
            )
        )
    if len(parts) == 2 and parts[0] == "tasks" and parts[1].isdigit():
        task = queries.get_task(conn, int(parts[1]))
        if task is None:
            return _not_found("작업이 없다")
        return _ok(
            views.task_page(
                task,
                queries.task_events(conn, task.id),
                queries.list_runs(conn, task_id=task.id, limit=1000),
                discord_url=settings.discord_url(task.discord_thread),
            )
        )
    if parts == ["runs"]:
        project, status = params.get("project", ""), params.get("status", "")
        runs = queries.list_runs(
            conn, project=project or None, status=status or None, limit=RUN_LIMIT
        )
        return _ok(
            views.runs_page(
                runs,
                projects=queries.projects(conn),
                project=project,
                status=status,
                limit=RUN_LIMIT,
            )
        )
    if len(parts) == 3 and parts[0] == "runs" and parts[2] == "log":
        return _log(settings, conn, parts[1])
    return _not_found("없는 주소다")


def _log(settings: DashboardSettings, conn: sqlite3.Connection, run_id: str) -> Response:
    run = queries.get_run(conn, run_id)
    if run is None or not run.log_path:
        return _not_found("실행 로그가 없다")
    path = Path(run.log_path).resolve()
    if not path.is_relative_to(settings.runs_dir.resolve()):
        # DB 값이 runs 폴더 밖을 가리키면 열지 않는다
        return Response(
            HTTPStatus.FORBIDDEN, views.message_page("열 수 없음", "runs 폴더 밖의 파일이다")
        )
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return _not_found("로그 파일이 지워졌다")
    return Response(HTTPStatus.OK, text, "text/plain; charset=utf-8")


def _ok(body: str) -> Response:
    return Response(HTTPStatus.OK, body)


def _not_found(message: str) -> Response:
    return Response(HTTPStatus.NOT_FOUND, views.message_page("찾을 수 없음", message))


def make_handler(settings: DashboardSettings) -> Callable[..., BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server 규약
            response = handle(settings, self.path)
            body = response.body.encode("utf-8")
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass  # 요청마다 터미널에 찍지 않는다

    return Handler


def serve(settings: DashboardSettings, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((HOST, port), make_handler(settings))
