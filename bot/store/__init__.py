"""SQLite 저장 계층 (SPEC 8)."""

from bot.store.db import SCHEMA_VERSION, SchemaVersionError, connect, migrate, schema_version
from bot.store.repo import (
    INVALID_OUTPUT,
    RUNNING,
    Actor,
    AgentRunRecord,
    EventKind,
    EventRecord,
    NewEvent,
    NotFoundError,
    Repository,
    StaleStateError,
    TaskRecord,
)

__all__ = [
    "INVALID_OUTPUT",
    "RUNNING",
    "SCHEMA_VERSION",
    "Actor",
    "AgentRunRecord",
    "EventKind",
    "EventRecord",
    "NewEvent",
    "NotFoundError",
    "Repository",
    "SchemaVersionError",
    "StaleStateError",
    "TaskRecord",
    "connect",
    "migrate",
    "schema_version",
]
