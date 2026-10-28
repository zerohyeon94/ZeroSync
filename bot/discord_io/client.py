"""Discord 연결 (SPEC 2.1, 4, 6.1).

- 포럼 게시글과 그 안의 Zero 메시지를 엔진에 넘긴다. Zero 외 입력, 봇·웹훅 메시지는 무시한다
- 슬래시 명령은 서버(guild) 명령으로 등록한다. Discord는 3초 안에 응답을 요구하므로
  먼저 접수 응답을 보내고 엔진 작업은 백그라운드 태스크로 실행한다
- 시작하면 포럼 채널마다 웹훅을 찾거나 만들고(Q6), 재시작 전에 끝나지 않은 실행을 정리한다(Q8)
"""

import asyncio
import logging
from collections.abc import Coroutine, Mapping
from typing import Any

import discord
from discord import app_commands

from bot.agents.base import AgentName, AgentRunner
from bot.clock import Clock, SystemClock
from bot.config import Config
from bot.discord_io.chat import DiscordChat
from bot.discord_io.rules import (
    WEBHOOK_NAME,
    IncomingMessage,
    MessageKind,
    classify,
    command_error,
)
from bot.github import GitHubClient
from bot.render.status import render_ping, render_status
from bot.store import Repository
from bot.workflow.engine import Engine, ProjectContext
from bot.workflow.mentions import Moment, should_mention
from bot.workflow.state import CommandName, Limits, TaskState

log = logging.getLogger(__name__)

EMPTY_POST = "(본문 없음)"
ACTIVE_STATES = {state for state in TaskState if not state.is_terminal}


def project_contexts(config: Config) -> dict[str, ProjectContext]:
    """설정의 프로젝트를 엔진 실행 정보로 바꾼다. 볼트 `기능/` 폴더는 읽기만 한다."""
    return {
        key: ProjectContext(
            repo=project.repo,
            base_branch=project.base_branch,
            test_command=project.test,
            github=GitHubClient(project.github),
            feature_dir=config.paths.vault_projects / project.vault_dir / "기능",
        )
        for key, project in config.projects.items()
    }


class ZeroSyncBot(discord.Client):
    def __init__(
        self,
        config: Config,
        repo: Repository,
        runners: Mapping[AgentName, AgentRunner],
        *,
        clock: Clock | None = None,
        git: Any = None,
        tests: Any = None,
    ):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.config = config
        self.repo = repo
        self.clock = clock or SystemClock()
        self.zero_user_id = int(config.secrets.zero_user_id)
        self.guild_ref = discord.Object(int(config.secrets.discord_guild_id))
        self.ops_channel_id = int(config.secrets.ops_channel_id)
        self.forums: dict[int, str] = {
            int(project.forum_channel_id): key for key, project in config.projects.items()
        }
        self.tree = app_commands.CommandTree(self)
        self.chat = DiscordChat(
            zero_user_id=self.zero_user_id,
            webhook_for=self._webhook_for,
            ops_channel=self._ops_channel,
        )
        self.engine = Engine(
            repo,
            self.chat,
            runners,
            project_contexts(config),
            timeout_sec=config.limits.cli_timeout_sec,
            git=git,
            tests=tests,
            limits=Limits(
                max_review_rounds=config.limits.max_review_rounds,
                max_test_retries=config.limits.max_test_retries,
            ),
            worktrees_dir=config.paths.worktrees,
            thread_url=self.thread_url,
        )
        self._webhooks: dict[int, discord.Webhook] = {}
        self._background: set[asyncio.Task[None]] = set()
        self._started = False
        self.startup_error: Exception | None = None
        _register_commands(self)

    # 시작

    async def setup_hook(self) -> None:
        await self.tree.sync(guild=self.guild_ref)

    async def on_ready(self) -> None:
        # 재연결 때도 on_ready가 다시 오므로 처음 한 번만 준비한다
        if self._started:
            return
        self._started = True
        log.info("Discord 연결: %s", self.user)
        try:
            await self._prepare_webhooks()
        except Exception as error:
            # 웹훅 없이 떠 있으면 게시글을 받아도 답할 수 없다. 알리고 종료한다
            log.exception("시작 준비 실패")
            self.startup_error = error
            try:
                await self.chat.notify_ops(
                    f"ZeroSync 봇 시작 실패: {error}", mention=should_mention(Moment.BOT_ERROR)
                )
            except Exception:
                log.exception("운영 채널 알림 실패")
            await self.close()
            return
        await self.engine.recover_interrupted()
        await self.engine.prepare_github()
        self._merge_poller = asyncio.create_task(self._poll_merges())
        await self.chat.notify_ops(
            f"ZeroSync 봇을 시작했다. 프로젝트: {', '.join(self.config.projects)}",
            mention=should_mention(Moment.NOTICE),
        )

    def thread_url(self, thread: str) -> str:
        return f"https://discord.com/channels/{self.guild_ref.id}/{thread}"

    async def _poll_merges(self) -> None:
        """AWAIT_MERGE 작업의 PR merge를 주기적으로 확인한다 (SPEC 6.2)."""
        while not self.is_closed():
            try:
                await self.engine.poll_merges()
            except Exception:
                log.exception("merge 확인 실패")
            await asyncio.sleep(self.config.limits.merge_poll_sec)

    async def close(self) -> None:
        poller = getattr(self, "_merge_poller", None)
        if poller is not None:
            poller.cancel()
        await super().close()

    async def _prepare_webhooks(self) -> None:
        assert self.user is not None
        for forum_id, project in self.forums.items():
            try:
                channel = self.get_channel(forum_id) or await self.fetch_channel(forum_id)
            except (discord.NotFound, discord.Forbidden) as error:
                raise RuntimeError(
                    f"{project}의 forum_channel_id 채널을 찾을 수 없거나 볼 권한이 없다"
                ) from error
            if not isinstance(channel, discord.ForumChannel):
                name = getattr(channel, "name", "?")
                raise RuntimeError(
                    f"{project}의 forum_channel_id가 포럼 채널이 아니다 "
                    f"(#{name}, 종류 {getattr(channel, 'type', '?')})"
                )
            hooks = await channel.webhooks()
            hook = next(
                (
                    h
                    for h in hooks
                    if h.name == WEBHOOK_NAME and h.user is not None and h.user.id == self.user.id
                ),
                None,
            )
            if hook is None:
                hook = await channel.create_webhook(name=WEBHOOK_NAME, reason="ZeroSync 게시용")
                log.info("웹훅 생성: %s", project)
            self._webhooks[forum_id] = hook

    async def _webhook_for(self, thread_id: int) -> discord.Webhook:
        thread = self.get_channel(thread_id) or await self.fetch_channel(thread_id)
        parent_id = getattr(thread, "parent_id", None)
        if parent_id not in self._webhooks:
            raise RuntimeError(f"스레드 {thread_id}의 포럼 웹훅이 없다")
        return self._webhooks[parent_id]

    async def _ops_channel(self) -> Any:
        return self.get_channel(self.ops_channel_id) or await self.fetch_channel(
            self.ops_channel_id
        )

    # 메시지

    async def on_message(self, message: discord.Message) -> None:
        incoming = IncomingMessage(
            message_id=message.id,
            author_id=message.author.id,
            from_bot=message.author.bot or message.webhook_id is not None,
            channel_id=message.channel.id,
            parent_id=getattr(message.channel, "parent_id", None),
        )
        kind = classify(incoming, zero_user_id=self.zero_user_id, forum_ids=self.forums)
        if kind is MessageKind.IGNORE:
            return
        assert incoming.parent_id is not None
        thread = str(message.channel.id)
        if kind is MessageKind.POST:
            project = self.forums[incoming.parent_id]
            title = getattr(message.channel, "name", "")
            text = message.content.strip() or EMPTY_POST
            self.spawn(
                self.engine.on_post(project=project, thread=thread, title=title, text=text),
                f"게시글 {thread}",
            )
        else:
            self.spawn(
                self.engine.on_message(thread, message.content, message_id=str(message.id)),
                f"메시지 {message.id}",
            )

    # 명령

    async def run_command(
        self, interaction: discord.Interaction, name: CommandName, arg: str = ""
    ) -> None:
        error = command_error(
            user_id=interaction.user.id,
            zero_user_id=self.zero_user_id,
            parent_id=getattr(interaction.channel, "parent_id", None),
            forum_ids=self.forums,
        )
        thread = str(interaction.channel_id)
        if error is None and await self.repo.find_task_by_thread(thread) is None:
            error = "이 게시글에 연결된 작업이 없다."
        if error is not None:
            await interaction.response.send_message(error, ephemeral=True)
            return
        # 명령을 게시글 흐름에 남긴다 (2026-10-10 Zero 결정)
        echo = f"/{name.value} {arg}".rstrip()
        await interaction.response.send_message(echo, silent=True)
        self.spawn(self.engine.on_command(thread, name, arg), echo)

    async def show_status(self, interaction: discord.Interaction) -> None:
        error = command_error(
            user_id=interaction.user.id,
            zero_user_id=self.zero_user_id,
            parent_id=getattr(interaction.channel, "parent_id", None),
            forum_ids=self.forums,
        )
        task = None if error else await self.repo.find_task_by_thread(str(interaction.channel_id))
        if error is None and task is None:
            error = "이 게시글에 연결된 작업이 없다."
        text = error if task is None else render_status(task, self.clock.now())
        await interaction.response.send_message(text, ephemeral=True)

    async def show_ping(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.zero_user_id:
            await interaction.response.send_message(
                "이 봇의 명령은 Zero만 쓸 수 있다.", ephemeral=True
            )
            return
        running = await self.repo.list_running_agent_runs()
        active = await self.repo.list_tasks(ACTIVE_STATES)
        text = render_ping(running_cli=len(running), active_tasks=len(active))
        await interaction.response.send_message(text, ephemeral=True)

    # 백그라운드 실행

    def spawn(self, work: Coroutine[Any, Any, Any], label: str) -> None:
        task = asyncio.create_task(self._guard(work, label))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _guard(self, work: Coroutine[Any, Any, Any], label: str) -> None:
        try:
            await work
        except Exception as error:
            log.exception("%s 처리 중 오류", label)
            try:
                await self.chat.notify_ops(
                    f"{label} 처리 중 오류: {type(error).__name__}: {error}",
                    mention=should_mention(Moment.BOT_ERROR),
                )
            except Exception:
                log.exception("운영 채널 알림 실패")


def _register_commands(bot: ZeroSyncBot) -> None:
    tree, guild = bot.tree, bot.guild_ref

    @tree.command(name="debate", description="두 에이전트가 서로의 의견에 반박 1회", guild=guild)
    async def debate(interaction: discord.Interaction) -> None:
        await bot.run_command(interaction, CommandName.DEBATE)

    @tree.command(name="decide", description="방향을 확정하고 다음 단계로 넘어간다", guild=guild)
    @app_commands.rename(direction="방향")
    @app_commands.describe(direction="확정할 방향")
    async def decide(interaction: discord.Interaction, direction: str) -> None:
        await bot.run_command(interaction, CommandName.DECIDE, direction)

    @tree.command(
        name="stop", description="작업을 멈추고 실행 중인 에이전트를 종료한다", guild=guild
    )
    async def stop(interaction: discord.Interaction) -> None:
        await bot.run_command(interaction, CommandName.STOP)

    @tree.command(name="approve", description="설계를 승인하고 구현을 시작한다", guild=guild)
    async def approve(interaction: discord.Interaction) -> None:
        await bot.run_command(interaction, CommandName.APPROVE)

    @tree.command(name="revise", description="설계를 고쳐 달라고 요청한다", guild=guild)
    @app_commands.rename(request="요청")
    @app_commands.describe(request="고칠 내용")
    async def revise(interaction: discord.Interaction, request: str) -> None:
        await bot.run_command(interaction, CommandName.REVISE, request)

    @tree.command(name="fix", description="merge 전에 [권장] 지적을 1회 반영한다", guild=guild)
    async def fix(interaction: discord.Interaction) -> None:
        await bot.run_command(interaction, CommandName.FIX, "권장 반영")

    @tree.command(name="resume", description="확인 필요 상태에서 직전 단계로 재개한다", guild=guild)
    async def resume(interaction: discord.Interaction) -> None:
        await bot.run_command(interaction, CommandName.RESUME)

    @tree.command(name="status", description="이 작업의 상태와 진행 횟수", guild=guild)
    async def status(interaction: discord.Interaction) -> None:
        await bot.show_status(interaction)

    @tree.command(name="ping", description="봇 생존과 실행 중인 CLI 수", guild=guild)
    async def ping(interaction: discord.Interaction) -> None:
        await bot.show_ping(interaction)


async def run_bot(config: Config) -> None:
    """DB를 열고 러너·엔진·Discord 클라이언트를 연결해 종료될 때까지 실행한다."""
    from bot.agents import ClaudeCliRunner, CodexCliRunner, ProcessRunner
    from bot.github import GitOps
    from bot.store import connect
    from bot.testrun import TestRunner

    conn = await connect(config.paths.db)
    try:
        process = ProcessRunner(config.paths.runs)
        runners: dict[AgentName, AgentRunner] = {
            "claude": ClaudeCliRunner(process, config.cli.claude, config.cli.claude_models),
            "codex": CodexCliRunner(process, config.cli.codex, config.cli.codex_models),
        }
        tests = TestRunner(
            process,
            concurrent=config.limits.concurrent_builds,
            timeout_sec=config.limits.cli_timeout_sec,
        )
        bot = ZeroSyncBot(
            config, Repository(conn, SystemClock()), runners, git=GitOps(), tests=tests
        )
        async with bot:
            await bot.start(config.secrets.discord_token.get_secret_value())
        if bot.startup_error is not None:
            raise bot.startup_error
    finally:
        await conn.close()
