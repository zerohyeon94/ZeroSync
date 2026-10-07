"""봇 설정 로더: `bot/projects.yaml` + `.env` (SPEC 9.1, 9.2).

- 실제 값 파일(`bot/projects.yaml`, `.env`)은 커밋하지 않는다. 예시는 `bot/projects.example.yaml`,
  `.env.example`에 있다 (SPEC Q11)
- 오류 메시지에는 키 이름과 위치만 담고 값은 넣지 않는다. 토큰이 로그에 섞이지 않게 하기 위해서다
- `.env`보다 실제 환경변수가 우선한다 (launchd plist의 EnvironmentVariables 등)
"""

import os
import re
import shlex
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECTS_PATH = PACKAGE_DIR / "projects.yaml"
DEFAULT_ENV_PATH = PACKAGE_DIR.parent / ".env"

ENV_KEYS = ("DISCORD_TOKEN", "DISCORD_GUILD_ID", "ZERO_USER_ID", "OPS_CHANNEL_ID")

_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
_GITHUB_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_ENV_LINE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


class ConfigError(ValueError):
    """설정 파일이 없거나 형식이 틀렸다. 메시지에 값은 담지 않는다."""


def _expand_path(value: Path) -> Path:
    path = value.expanduser()
    if not path.is_absolute():
        raise ValueError("절대 경로이거나 ~로 시작해야 한다")
    return path


ExpandedPath = Annotated[Path, AfterValidator(_expand_path)]
DiscordId = Annotated[str, Field(pattern=r"^[0-9]{1,20}$")]


class _Model(BaseModel):
    # 오타 난 키를 조용히 무시하지 않는다
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class ProjectConfig(_Model):
    forum_channel_id: DiscordId
    repo: ExpandedPath
    github: str = Field(pattern=_GITHUB_REPO.pattern)
    base_branch: str = "develop"
    # 셸을 거치지 않고 실행하므로 인자 목록으로 나눠 둔다 (SPEC 2.1)
    test: tuple[str, ...]
    vault_dir: str = Field(min_length=1)
    vault_hub: str = Field(min_length=1)
    vault_tag: str = Field(min_length=1)
    vault_slug: str = Field(min_length=1)

    @field_validator("base_branch")
    @classmethod
    def _not_main(cls, value: str) -> str:
        # 봇은 main에 접근하지 않는다 (SPEC 9.5)
        if value == "main":
            raise ValueError("기준 브랜치로 main을 쓸 수 없다")
        return value

    @field_validator("test", mode="before")
    @classmethod
    def _split_test(cls, value: object) -> object:
        if isinstance(value, str):
            try:
                value = shlex.split(value)
            except ValueError as error:
                raise ValueError("test 명령의 따옴표가 닫히지 않았다") from error
        if not value:
            raise ValueError("test 명령이 비어 있다")
        return value


class PathsConfig(_Model):
    vault_projects: ExpandedPath
    worktrees: ExpandedPath = Path("~/.zerosync/worktrees")
    runs: ExpandedPath = Path("~/.zerosync/runs")
    db: ExpandedPath = Path("~/.zerosync/zerosync.db")

    @property
    def lock(self) -> Path:
        # 단일 인스턴스 락은 DB와 같은 폴더에 둔다.
        # 한 DB를 두 봇이 함께 쓰지 않게 하는 것이 목적이다
        return self.db.parent / "bot.lock"


class CliConfig(_Model):
    # launchd PATH에서 못 찾으면 절대 경로를 적는다 (SPEC 5.2)
    claude: str = Field(default="claude", min_length=1)
    codex: str = Field(default="codex", min_length=1)


class LimitsConfig(_Model):
    max_review_rounds: int = Field(default=3, ge=1)
    max_test_retries: int = Field(default=2, ge=0)
    cli_timeout_sec: int = Field(default=3600, ge=1)
    concurrent_builds: int = Field(default=1, ge=1)
    merge_poll_sec: int = Field(default=300, ge=1)
    remind_after_hours: int = Field(default=24, ge=1)


class ProjectsFile(_Model):
    projects: dict[str, ProjectConfig] = Field(min_length=1)
    paths: PathsConfig
    cli: CliConfig = CliConfig()
    limits: LimitsConfig = LimitsConfig()

    @field_validator("projects")
    @classmethod
    def _check_keys(cls, value: dict[str, ProjectConfig]) -> dict[str, ProjectConfig]:
        for key in value:
            if not _PROJECT_KEY.match(key):
                raise ValueError(f"프로젝트 키 {key!r}는 영문 소문자·숫자·-만 쓴다 (40자 이내)")
        return value

    @model_validator(mode="after")
    def _unique_forums(self) -> "ProjectsFile":
        seen: dict[str, str] = {}
        for key, project in self.projects.items():
            other = seen.setdefault(project.forum_channel_id, key)
            if other != key:
                raise ValueError(f"프로젝트 {other}와 {key}의 forum_channel_id가 같다")
        return self


class Secrets(_Model):
    discord_token: SecretStr = Field(min_length=1)
    discord_guild_id: DiscordId
    zero_user_id: DiscordId
    ops_channel_id: DiscordId


class Config(_Model):
    projects: dict[str, ProjectConfig]
    paths: PathsConfig
    cli: CliConfig
    limits: LimitsConfig
    secrets: Secrets

    def project_for_forum(self, channel_id: str) -> str | None:
        """포럼 채널 ID로 프로젝트 키를 찾는다. 등록되지 않은 채널이면 None."""
        for key, project in self.projects.items():
            if project.forum_channel_id == channel_id:
                return key
        return None


def parse_env(text: str) -> dict[str, str]:
    """`.env` 내용을 읽는다.

    빈 줄과 `#` 주석 줄은 건너뛰고, `export ` 접두어와 값을 감싼 따옴표를 허용한다.
    """
    values: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _ENV_LINE.match(line)
        if match is None:
            raise ConfigError(f".env {number}번째 줄이 KEY=VALUE 형식이 아니다")
        key, value = match.group(1), match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key in values:
            raise ConfigError(f".env에 {key}가 두 번 있다 ({number}번째 줄)")
        values[key] = value
    return values


def load_config(
    projects_path: Path = DEFAULT_PROJECTS_PATH,
    env_path: Path = DEFAULT_ENV_PATH,
    environ: Mapping[str, str] | None = None,
) -> Config:
    """설정을 읽어 검증한다. `.env` 파일은 없어도 되지만 필요한 키는 환경변수로라도 있어야 한다."""
    environ = os.environ if environ is None else environ

    try:
        raw = yaml.safe_load(projects_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(
            f"{projects_path} 파일이 없다. projects.example.yaml을 복사해 값을 채운다"
        ) from None
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        where = f" ({mark.line + 1}번째 줄)" if mark is not None else ""
        raise ConfigError(f"{projects_path.name}의 YAML 형식이 틀렸다{where}") from None
    if not isinstance(raw, dict):
        raise ConfigError(f"{projects_path.name}의 최상위는 매핑이어야 한다")

    try:
        env_file = parse_env(env_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        env_file = {}
    merged = {key: environ.get(key, env_file.get(key)) for key in ENV_KEYS}
    missing = [key for key, value in merged.items() if not value]
    if missing:
        raise ConfigError(f"환경변수가 없다: {', '.join(missing)} (.env.example 참고)")

    try:
        projects = ProjectsFile.model_validate(raw)
        secrets = Secrets.model_validate({key.lower(): value for key, value in merged.items()})
    except ValidationError as error:
        raise ConfigError(_describe(error)) from None
    return Config(
        projects=projects.projects,
        paths=projects.paths,
        cli=projects.cli,
        limits=projects.limits,
        secrets=secrets,
    )


def _describe(error: ValidationError) -> str:
    # 입력값(토큰일 수 있음)은 빼고 위치와 이유만 남긴다
    lines = []
    for item in error.errors(include_input=False, include_url=False):
        where = ".".join(str(part) for part in item["loc"]) or "(최상위)"
        lines.append(f"- {where}: {item['msg']}")
    return "설정 값이 틀렸다\n" + "\n".join(lines)
