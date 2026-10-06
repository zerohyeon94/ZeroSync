"""SQLite 연결과 스키마 버전 관리 (SPEC 8).

스키마 버전은 `PRAGMA user_version`으로 관리한다. MIGRATIONS[i]는 버전 i에서 i+1로 올리는 SQL이다.
연결은 자동 커밋 모드로 열고, 트랜잭션은 저장소(repo)가 BEGIN/COMMIT으로 직접 연다.
"""

from pathlib import Path

import aiosqlite

_V1 = """
CREATE TABLE tasks (
  id               INTEGER PRIMARY KEY,
  project          TEXT NOT NULL,
  discord_thread   TEXT NOT NULL UNIQUE,
  title            TEXT NOT NULL,
  state            TEXT NOT NULL,
  prev_state       TEXT,
  review_round     INTEGER NOT NULL DEFAULT 0,
  test_retry       INTEGER NOT NULL DEFAULT 0,
  opinion_rounds   INTEGER NOT NULL DEFAULT 0,
  issue_number     INTEGER,
  pr_number        INTEGER,
  branch           TEXT,
  worktree         TEXT,
  claude_session   TEXT,
  waiting_since    TEXT,
  reminded_at      TEXT,
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL
);

CREATE TABLE events (
  id               INTEGER PRIMARY KEY,
  task_id          INTEGER NOT NULL REFERENCES tasks(id),
  actor            TEXT NOT NULL,
  kind             TEXT NOT NULL,
  payload          TEXT NOT NULL,
  discord_message  TEXT,
  created_at       TEXT NOT NULL
);
CREATE INDEX events_task ON events(task_id, id);

CREATE TABLE agent_runs (
  id               TEXT PRIMARY KEY,
  task_id          INTEGER NOT NULL REFERENCES tasks(id),
  agent            TEXT NOT NULL,
  stage            TEXT NOT NULL,
  exit_code        INTEGER,
  status           TEXT NOT NULL,
  log_path         TEXT,
  started_at       TEXT NOT NULL,
  finished_at      TEXT
);
CREATE INDEX agent_runs_task ON agent_runs(task_id);
"""

MIGRATIONS: tuple[str, ...] = (_V1,)
SCHEMA_VERSION = len(MIGRATIONS)


class SchemaVersionError(RuntimeError):
    """DB 스키마가 이 코드보다 새 버전이다."""


async def connect(path: Path | str) -> aiosqlite.Connection:
    """DB를 열고 최신 스키마로 올린다. path가 ":memory:"이면 메모리 DB."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(path, isolation_level=None)
    conn.row_factory = aiosqlite.Row
    try:
        await conn.execute("PRAGMA foreign_keys = ON")
        await migrate(conn)
    except BaseException:
        await conn.close()
        raise
    return conn


async def schema_version(conn: aiosqlite.Connection) -> int:
    async with conn.execute("PRAGMA user_version") as cursor:
        row = await cursor.fetchone()
    assert row is not None
    return int(row[0])


async def migrate(conn: aiosqlite.Connection) -> int:
    current = await schema_version(conn)
    if current > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"DB 스키마 버전 {current}이 코드가 아는 최신 버전 {SCHEMA_VERSION}보다 높다"
        )
    for version in range(current, SCHEMA_VERSION):
        # 마이그레이션 하나와 버전 기록을 한 트랜잭션으로 묶는다
        await conn.executescript(
            f"BEGIN;\n{MIGRATIONS[version]}\nPRAGMA user_version = {version + 1};\nCOMMIT;"
        )
    return SCHEMA_VERSION
