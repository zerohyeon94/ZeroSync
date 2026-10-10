from pathlib import Path

import pytest

from bot.agents import Stage
from bot.config import PACKAGE_DIR, ConfigError, load_config, parse_env

EXAMPLE = PACKAGE_DIR / "projects.example.yaml"
ENV_EXAMPLE = PACKAGE_DIR.parent / ".env.example"

ENV = {
    "DISCORD_TOKEN": "token-secret-value",
    "DISCORD_GUILD_ID": "111",
    "ZERO_USER_ID": "222",
    "OPS_CHANNEL_ID": "333",
}

TEST_LINE = (
    "    test: xcodebuild test -scheme Gagessi"
    " -destination 'platform=iOS Simulator,name=iPhone 16'\n"
)
PROJECT = (
    """\
    forum_channel_id: "100"
    repo: ~/Dev/Gagessi
    github: owner/Gagessi
"""
    + TEST_LINE
    + """\
    vault_dir: 일일 예산 관리 앱
    vault_hub: 가게씨.md
    vault_tag: brain/gagaessi
    vault_slug: gagaessi
"""
)


def yaml_text(project=PROJECT, extra=""):
    return f"projects:\n  gagessi:\n{project}paths:\n  vault_projects: /vault/Projects\n{extra}"


def write(tmp_path, text, name="projects.yaml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def load(tmp_path, text=None, environ=ENV, env_text=None):
    projects = write(tmp_path, yaml_text() if text is None else text)
    env_path = tmp_path / ".env"
    if env_text is not None:
        env_path.write_text(env_text, encoding="utf-8")
    return load_config(projects, env_path, environ)


# 정상 로드


def test_loads_project_with_defaults(tmp_path):
    config = load(tmp_path)
    project = config.projects["gagessi"]
    assert project.repo == Path.home() / "Dev/Gagessi"
    assert project.base_branch == "develop"
    assert project.test == (
        "xcodebuild",
        "test",
        "-scheme",
        "Gagessi",
        "-destination",
        "platform=iOS Simulator,name=iPhone 16",
    )
    assert config.paths.db == Path.home() / ".zerosync/zerosync.db"
    assert config.paths.lock == Path.home() / ".zerosync/bot.lock"
    assert config.cli.claude == "claude"
    assert config.limits.max_review_rounds == 3
    assert config.limits.max_test_retries == 2
    assert config.limits.cli_timeout_sec == 3600


def test_test_command_may_be_a_list(tmp_path):
    project = PROJECT.replace(
        TEST_LINE,
        "    test: [swift, test]\n",
    )
    assert load(tmp_path, yaml_text(project)).projects["gagessi"].test == ("swift", "test")


def test_overrides_limits_and_paths(tmp_path):
    extra = "limits:\n  max_review_rounds: 5\ncli:\n  claude: /opt/bin/claude\n"
    text = yaml_text(extra=extra).replace(
        "  vault_projects: /vault/Projects\n",
        "  vault_projects: /vault/Projects\n  db: /data/zs.db\n",
    )
    config = load(tmp_path, text)
    assert config.limits.max_review_rounds == 5
    assert config.limits.max_test_retries == 2
    assert config.cli.claude == "/opt/bin/claude"
    assert config.paths.lock == Path("/data/bot.lock")


def test_project_for_forum(tmp_path):
    config = load(tmp_path)
    assert config.project_for_forum("100") == "gagessi"
    assert config.project_for_forum("999") is None


def test_example_file_is_valid():
    environ = {key: "1" for key in ENV}
    config = load_config(EXAMPLE, Path("/nonexistent/.env"), environ)
    assert list(config.projects) == ["gagessi"]


def test_env_example_lists_every_key():
    assert set(parse_env(ENV_EXAMPLE.read_text(encoding="utf-8"))) == set(ENV)


# 프로젝트 설정 검증


@pytest.mark.parametrize(
    ("old", "new", "where"),
    [
        ('forum_channel_id: "100"', 'forum_channel_id: "abc"', "forum_channel_id"),
        ("repo: ~/Dev/Gagessi", "repo: Dev/Gagessi", "repo"),
        ("github: owner/Gagessi", "github: Gagessi", "github"),
        ("vault_slug: gagaessi", 'vault_slug: ""', "vault_slug"),
        ("vault_slug: gagaessi", "vault_slug: gagaessi\n    typo_key: 1", "typo_key"),
    ],
)
def test_rejects_invalid_project_field(tmp_path, old, new, where):
    with pytest.raises(ConfigError, match=f"projects.gagessi.{where}"):
        load(tmp_path, yaml_text(PROJECT.replace(old, new)))


def test_rejects_main_as_base_branch(tmp_path):
    project = PROJECT + "    base_branch: main\n"
    with pytest.raises(ConfigError, match="main"):
        load(tmp_path, yaml_text(project))


@pytest.mark.parametrize("test_value", ['""', "[]", '"xcodebuild \'unclosed"'])
def test_rejects_bad_test_command(tmp_path, test_value):
    project = PROJECT.replace(
        TEST_LINE,
        f"    test: {test_value}\n",
    )
    with pytest.raises(ConfigError, match="projects.gagessi.test"):
        load(tmp_path, yaml_text(project))


def test_rejects_bad_project_key(tmp_path):
    with pytest.raises(ConfigError, match="Gagessi"):
        load(tmp_path, yaml_text().replace("  gagessi:", "  Gagessi:"))


def test_rejects_duplicate_forum_channel(tmp_path):
    text = yaml_text().replace("paths:", "  jday:\n" + PROJECT + "paths:")
    with pytest.raises(ConfigError, match="forum_channel_id가 같다"):
        load(tmp_path, text)


def test_rejects_non_positive_limit(tmp_path):
    with pytest.raises(ConfigError, match="limits.max_review_rounds"):
        load(tmp_path, yaml_text(extra="limits:\n  max_review_rounds: 0\n"))


def test_requires_at_least_one_project(tmp_path):
    with pytest.raises(ConfigError, match="projects"):
        load(tmp_path, "projects: {}\npaths:\n  vault_projects: /vault\n")


# 파일 오류


def test_missing_projects_file(tmp_path):
    with pytest.raises(ConfigError, match="projects.example.yaml"):
        load_config(tmp_path / "projects.yaml", tmp_path / ".env", ENV)


def test_broken_yaml_reports_line(tmp_path):
    with pytest.raises(ConfigError, match="2번째 줄"):
        load(tmp_path, "projects: {}\nbad: key: value\n")


def test_top_level_must_be_mapping(tmp_path):
    with pytest.raises(ConfigError, match="최상위"):
        load(tmp_path, "- a\n- b\n")


# 환경변수


def test_reads_env_file_when_environ_is_empty(tmp_path):
    env_text = "\n".join(f"{key}={value}" for key, value in ENV.items())
    config = load(tmp_path, environ={}, env_text=env_text)
    assert config.secrets.discord_token.get_secret_value() == "token-secret-value"
    assert config.secrets.ops_channel_id == "333"


def test_environ_overrides_env_file(tmp_path):
    env_text = "\n".join(f"{key}={value}" for key, value in ENV.items())
    config = load(tmp_path, environ={"ZERO_USER_ID": "999"}, env_text=env_text)
    assert config.secrets.zero_user_id == "999"
    assert config.secrets.discord_guild_id == "111"


def test_reports_missing_env_keys(tmp_path):
    with pytest.raises(ConfigError, match="DISCORD_TOKEN, OPS_CHANNEL_ID"):
        load(tmp_path, environ={"DISCORD_GUILD_ID": "1", "ZERO_USER_ID": "2"})


def test_errors_and_repr_do_not_leak_token(tmp_path):
    bad = dict(ENV, DISCORD_GUILD_ID="not-a-number")
    with pytest.raises(ConfigError) as caught:
        load(tmp_path, environ=bad)
    assert "discord_guild_id" in str(caught.value)
    assert "token-secret-value" not in str(caught.value)
    assert "not-a-number" not in str(caught.value)

    config = load(tmp_path)
    assert "token-secret-value" not in repr(config)
    assert "token-secret-value" not in str(config.model_dump())


# .env 파싱


def test_parse_env_formats():
    text = "# 주석\n\nA=1\nexport B = two words \nC=\"quoted # not comment\"\nD='single'\nE=\n"
    assert parse_env(text) == {
        "A": "1",
        "B": "two words",
        "C": "quoted # not comment",
        "D": "single",
        "E": "",
    }


def test_parse_env_rejects_bad_line_without_value():
    with pytest.raises(ConfigError, match="2번째 줄") as caught:
        parse_env("A=1\nsecret-token-without-key\n")
    assert "secret-token" not in str(caught.value)


def test_parse_env_rejects_duplicate_key():
    with pytest.raises(ConfigError, match="A가 두 번"):
        parse_env("A=1\nA=2\n")


# 단계별 모델


def test_cli_models_by_stage(tmp_path):
    extra = (
        "cli:\n"
        "  claude_models:\n    opinion: sonnet\n    implement: opus\n"
        "  codex_models:\n    review: gpt-x\n"
    )
    config = load(tmp_path, yaml_text(extra=extra))
    assert config.cli.claude_models == {Stage.OPINION: "sonnet", Stage.IMPLEMENT: "opus"}
    assert config.cli.codex_models == {Stage.REVIEW: "gpt-x"}
    assert load(tmp_path).cli.claude_models == {}


@pytest.mark.parametrize(
    ("extra", "match"),
    [
        ("cli:\n  claude_models:\n    review: opus\n", "Claude가 맡지 않는 단계: review"),
        ("cli:\n  codex_models:\n    implement: gpt\n", "Codex가 맡지 않는 단계: implement"),
        ("cli:\n  claude_models:\n    opinon: sonnet\n", "cli.claude_models"),
        ("cli:\n  claude_models:\n    opinion: ''\n", "cli.claude_models"),
    ],
)
def test_rejects_bad_cli_models(tmp_path, extra, match):
    with pytest.raises(ConfigError, match=match):
        load(tmp_path, yaml_text(extra=extra))
