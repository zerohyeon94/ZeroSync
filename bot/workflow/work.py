"""설계부터 merge까지의 단계 작업 (운영 규약 1.5, 1.7~1.9, 3.3, 4장).

Engine이 이 클래스를 상속해 쓴다. 각 작업은 작업마다 하나씩(Engine._stage) 실행되고,
끝나면 (내부 이벤트, 기록할 이벤트)를 돌려준다. 엔진이 그 이벤트로 다음 상태를 정한다.

- 앱 저장소에 쓰는 것은 봇 전용 worktree(`<worktrees>/<project>-<Issue>`)뿐이다 (3.3)
- push는 GitOps가 보호 조건(4.7)을 검사한 뒤에만 한다. force push는 하지 않는다
- 에이전트 커밋은 push 전에 메시지 형식(4.4)을 검사하고, 틀리면 1회 고쳐 달라고 다시 요청한다
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bot.agents.base import Stage
from bot.github.rules import commit_message_problems
from bot.prompts import (
    design_prompt,
    fix_prompt,
    implement_prompt,
    persona_for,
    review_prompt,
)
from bot.render import render_format_error, render_notice
from bot.render.work import (
    ReviewRound,
    render_design,
    render_findings,
    render_implementation,
    render_issue_body,
    render_pr_body,
    render_review,
    render_test_report,
)
from bot.schemas import (
    FEATURE_NAMES,
    ISSUE_NUMBER,
    ChangeType,
    DesignSummary,
    ImplementationReport,
    Review,
)
from bot.store import Actor, EventKind, NewEvent
from bot.store.repo import TaskRecord
from bot.testrun import TestReport
from bot.workflow.mentions import Moment, should_mention
from bot.workflow.state import (
    FixSource,
    NoticeCode,
    ReviewFinished,
    StageFailed,
    StageSucceeded,
    TestsFinished,
)

if TYPE_CHECKING:
    from bot.workflow.engine import Outcome, ProjectContext, _Answer

log = logging.getLogger(__name__)

TYPE_LABELS = {
    ChangeType.FEATURE_ADD: "type:feature",
    ChangeType.FEATURE_CHANGE: "type:feature",
    ChangeType.BUG_FIX: "type:fix",
    ChangeType.INTERNAL: "type:refactor",
}
# 리뷰 프롬프트에 넣는 diff 최대 길이. 넘으면 잘라 내고 표시한다
MAX_DIFF_CHARS = 80_000


class WorkStages:
    # Engine이 채운다
    _repo: Any
    _chat: Any
    _git: Any
    _tests: Any
    _worktrees: Path
    _projects: Any
    _running: Any
    _thread_url: Any
    _org: Any
    _name: Any

    # 공통

    def _project(self, task: TaskRecord) -> ProjectContext:
        return self._projects[task.project]

    def _github(self, task: TaskRecord) -> Any:
        github = self._project(task).github
        if github is None:
            raise RuntimeError(f"{task.project}의 GitHub 연결이 없다")
        return github

    def _web(self, task: TaskRecord, path: str) -> str:
        return f"https://github.com/{self._github(task).repo}/{path}"

    async def _latest(self, task_id: int, kind: EventKind) -> dict[str, Any] | None:
        events = await self._repo.list_events(task_id, {kind})
        return events[-1].payload if events else None

    async def _decision(self, task_id: int) -> str:
        payload = await self._latest(task_id, EventKind.DECISION)
        return str(payload.get("text", "")) if payload else ""

    async def _summary(self, task_id: int) -> DesignSummary:
        payload = await self._latest(task_id, EventKind.DESIGN)
        if payload is None:
            raise RuntimeError("승인된 설계가 없다")
        return DesignSummary.model_validate(payload["summary"])

    async def _latest_report(self, task_id: int) -> ImplementationReport | None:
        events = await self._repo.list_events(task_id, {EventKind.IMPL, EventKind.FIX})
        if not events:
            return None
        return ImplementationReport.model_validate(events[-1].payload["report"])

    async def _latest_tests(self, task_id: int) -> TestReport | None:
        payload = await self._latest(task_id, EventKind.TEST)
        return TestReport.from_payload(payload) if payload else None

    async def _reviews(self, task_id: int) -> list[ReviewRound]:
        return [
            ReviewRound(event.payload["round"], Review.model_validate(event.payload["review"]))
            for event in await self._repo.list_events(task_id, {EventKind.REVIEW})
        ]

    def _worktree(self, task: TaskRecord) -> Path:
        if task.worktree is None:
            raise RuntimeError("작업 worktree가 없다")
        return Path(task.worktree)

    async def _commit_problems(self, task: TaskRecord, worktree: Path, before: int) -> list[str]:
        """에이전트 작업 뒤 확인: 커밋하지 않은 변경, 새 커밋 유무, 커밋 메시지 형식 (4.4)."""
        problems = []
        if not await self._git.is_clean(worktree):
            problems.append("커밋하지 않은 변경이 남아 있다. 모두 커밋한다")
        commits = await self._git.commits(worktree, self._project(task).base_branch)
        if len(commits) <= before:
            problems.append("새 커밋이 없다. 변경을 커밋한다")
        for commit in commits[before:]:
            for problem in commit_message_problems(commit.message, task.issue_number or 0):
                problems.append(f"커밋 {commit.sha[:7]}: {problem}")
        return problems

    async def _failed(self, task: TaskRecord, stage: str, answer: _Answer[Any]) -> Outcome:
        """에이전트 단계 실패. 원문이나 실패 안내를 게시하고 NEEDS_HUMAN으로 보낸다 (SPEC 3.3)."""
        name = self._name(answer.agent)
        if answer.failed_to_run:
            reason = f"{name} {stage} 실행 실패 ({answer.status})"
            await self._say(
                task, render_notice(NoticeCode.AGENT_FAILED, f"[{name}] {answer.status}")
            )
            await self._chat.notify_ops(
                f"[{task.project}] 작업 {task.id} {name} {stage} 실행 실패: {answer.status}. "
                f"로그: {answer.log_path}",
                mention=should_mention(Moment.BOT_ERROR),
            )
        else:
            reason = f"{name} {stage} 출력이 재요청 후에도 맞지 않았다"
            rendered = render_format_error(answer.raw, answer.error)
            await self._chat.post(
                task.discord_thread, answer.agent, rendered.text, attachments=rendered.attachments
            )
        payload = {"stage": stage, "reason": reason, "error": answer.error, "raw": answer.raw}
        return StageFailed(reason), NewEvent(Actor.BOT, EventKind.ERROR, payload)

    # Issue (운영 규약 1.8)

    async def _create_issue(self, task_id: int) -> Outcome | None:
        task = await self._repo.get_task(task_id)
        if task.issue_number is not None:
            return None
        decision = await self._decision(task_id)
        latest = await self._latest_opinions(task_id)
        opinions = [(self._name(agent), latest[agent]) for agent in latest]
        body = render_issue_body(
            decision=decision,
            post=await self._post_text(task),
            opinions=opinions,
            discord_url=self._thread_url(task.discord_thread),
        )
        number = await self._github(task).create_issue(task.title, body, ["zerosync"])
        task = await self._repo.update_fields(task.id, {"issue_number": number})
        url = self._web(task, f"issues/{number}")
        await self._say(
            task, render_notice(NoticeCode.DECISION_RECORDED, f"Issue #{number}: {url}")
        )
        return None

    # 설계 (운영 규약 3.3, 4.3)

    async def _design(self, task_id: int, revision: str) -> Outcome:
        task = await self._repo.get_task(task_id)
        if task.issue_number is None:
            # 재시작 등으로 Issue 없이 설계에 들어왔다
            await self._create_issue(task_id)
            task = await self._repo.get_task(task_id)
        project = self._project(task)
        issue = task.issue_number
        worktree = (
            Path(task.worktree) if task.worktree else self._worktrees / f"{task.project}-{issue}"
        )
        await self._git.prepare_worktree(project.repo, worktree, project.base_branch)
        task = await self._repo.update_fields(task.id, {"worktree": str(worktree)})
        before = len(await self._git.commits(worktree, project.base_branch))
        previous = None
        if await self._latest(task_id, EventKind.DESIGN):
            previous = await self._summary(task_id)

        features = project.feature_names()
        context: dict[str, Any] = {ISSUE_NUMBER: issue}
        if features is not None:
            context[FEATURE_NAMES] = features

        async def verify(summary: DesignSummary) -> list[str]:
            problems = []
            if not (worktree / summary.design_doc).is_file():
                problems.append(f"{summary.design_doc} 파일이 없다")
            return problems + await self._commit_problems(task, worktree, before)

        agent = self._org.roles.design
        verb = "설계를 시작한다" if not revision else "설계를 고친다"
        await self._say(task, f"{self._name(agent)}이 {verb}.")
        prompt = design_prompt(
            persona_for(self._org, agent),
            title=task.title,
            post=await self._post_text(task),
            decision=await self._decision(task_id),
            issue=issue,
            features=None if features is None else sorted(features),
            history=await self._history(task),
            revision=revision,
            previous=previous,
        )
        answer = await self._ask(
            task,
            agent,
            Stage.DESIGN,
            prompt,
            model=DesignSummary,
            mode="write_worktree",
            cwd=worktree,
            context=context,
            resume=task.claude_session if revision else None,
            verify=verify,
        )
        if answer.result is None:
            return await self._failed(task, "설계", answer)
        summary: DesignSummary = answer.result
        task = await self._repo.update_fields(task.id, {"claude_session": answer.session_id})
        branch = await self._push_design_branch(task, worktree, summary.branch_name(issue))

        doc_url = self._web(task, f"blob/{branch}/{summary.design_doc}")
        await self._github(task).comment_issue(issue, render_design(summary, doc_url=doc_url))
        message_id = await self._chat.post(
            task.discord_thread,
            agent,
            render_design(summary, doc_url=doc_url)
            + "\n\n`/approve`로 승인하거나 `/revise <요청>`으로 고친다.",
            mention=should_mention(Moment.DESIGN_READY),
        )
        payload = {
            "summary": summary.model_dump(mode="json"),
            "revision": revision,
            "branch": branch,
        }
        return StageSucceeded(), NewEvent(agent, EventKind.DESIGN, payload, message_id)

    async def _push_design_branch(self, task: TaskRecord, worktree: Path, branch: str) -> str:
        """설계 커밋에 작업 브랜치를 만들어 push한다 (4.3).

        설계 수정으로 이름이 바뀌면 옛 원격 브랜치를 지운다.
        """
        old = task.branch
        if old is None:
            await self._git.create_branch(worktree, branch)
        elif old != branch:
            await self._git.rename_branch(worktree, old, branch)
        # push 보호는 SQLite에 기록된 이름과 비교하므로 먼저 기록한다 (4.7)
        await self._repo.update_fields(task.id, {"branch": branch})
        await self._git.push(worktree, branch, recorded=branch)
        if old is not None and old != branch:
            await self._git.delete_remote_branch(worktree, old, recorded=old)
        return branch

    async def _apply_type_label(self, task: TaskRecord) -> None:
        summary = await self._summary(task.id)
        if task.issue_number is not None:
            await self._github(task).add_labels(
                task.issue_number, [TYPE_LABELS[summary.change_type]]
            )

    # 구현과 수정

    async def _implement(self, task_id: int) -> Outcome:
        task = await self._repo.get_task(task_id)
        summary = await self._summary(task_id)
        agent = self._org.roles.implement
        prompt = implement_prompt(
            persona_for(self._org, agent),
            title=task.title,
            decision=await self._decision(task_id),
            issue=task.issue_number,
            branch=task.branch,
            summary=summary,
        )
        await self._say(task, f"{self._name(agent)}이 구현을 시작한다.", Moment.IMPLEMENT_STARTED)
        return await self._work(task, Stage.IMPLEMENT, prompt, EventKind.IMPL, {}, "구현")

    async def _fix(self, task_id: int, source: FixSource) -> Outcome:
        task = await self._repo.get_task(task_id)
        summary = await self._summary(task_id)
        if source is FixSource.RESUME:
            last = await self._latest(task_id, EventKind.FIX)
            source = FixSource(last["source"]) if last else FixSource.TESTS
            if source is FixSource.RESUME:  # pragma: no cover - 기록에는 RESUME이 남지 않는다
                source = FixSource.TESTS
        problems = await self._fix_problems(task_id, source)
        prompt = fix_prompt(
            persona_for(self._org, self._org.roles.implement),
            title=task.title,
            issue=task.issue_number,
            branch=task.branch,
            summary=summary,
            problems=problems,
        )
        labels = {
            FixSource.TESTS: "테스트 실패",
            FixSource.REVIEW: "리뷰 [필수] 지적",
            FixSource.RECOMMENDED: "[권장] 지적",
        }
        name = self._name(self._org.roles.implement)
        await self._say(task, f"{name}이 고친다: {labels[source]}", Moment.IMPLEMENT_STARTED)
        payload = {"source": source.value}
        return await self._work(task, Stage.FIX, prompt, EventKind.FIX, payload, "수정")

    async def _fix_problems(self, task_id: int, source: FixSource) -> str:
        if source is FixSource.TESTS:
            tests = await self._latest_tests(task_id)
            body = render_test_report(tests) if tests else "테스트 결과가 없다"
            return f"봇이 실행한 테스트가 실패했다.\n\n{body}"
        reviews = await self._reviews(task_id)
        if not reviews:
            raise RuntimeError("리뷰 결과가 없다")
        review = reviews[-1].review
        if source is FixSource.RECOMMENDED:
            return "Zero가 merge 전에 [권장] 지적 반영을 요청했다.\n\n" + render_findings(
                review.recommended_findings
            )
        required = render_findings(review.required_findings)
        reviewer = self._name(self._org.roles.review)
        text = f"{reviewer}의 [필수] 지적 (번호마다 대응한다):\n\n{required}"
        if review.recommended_findings:
            text += (
                "\n\n참고: [권장] 지적 (반영 여부는 판단에 맡긴다. 번호 대응 대상 아님)\n\n"
                + render_findings(review.recommended_findings)
            )
        return text

    async def _work(
        self,
        task: TaskRecord,
        stage: Stage,
        prompt: str,
        kind: EventKind,
        payload: dict[str, Any],
        label: str,
    ) -> Outcome:
        worktree = self._worktree(task)
        base = self._project(task).base_branch
        before = len(await self._git.commits(worktree, base))

        async def verify(_report: ImplementationReport) -> list[str]:
            return await self._commit_problems(task, worktree, before)

        agent = self._org.roles.implement
        answer = await self._ask(
            task,
            agent,
            stage,
            prompt,
            model=ImplementationReport,
            mode="write_worktree",
            cwd=worktree,
            resume=task.claude_session,
            verify=verify,
        )
        if answer.result is None:
            return await self._failed(task, label, answer)
        report: ImplementationReport = answer.result
        if answer.session_id:
            task = await self._repo.update_fields(task.id, {"claude_session": answer.session_id})
        await self._git.push(worktree, task.branch, recorded=task.branch)
        commits = await self._git.commits(worktree, base)
        message_id = await self._chat.post(
            task.discord_thread,
            agent,
            render_implementation(report, heading=label),
            mention=should_mention(Moment.IMPLEMENT_STARTED),
        )
        data = {
            **payload,
            "report": report.model_dump(mode="json"),
            "commits": [commit.sha for commit in commits[before:]],
        }
        return StageSucceeded(), NewEvent(agent, kind, data, message_id)

    # 테스트 (운영 규약 1.7)

    async def _run_tests(self, task_id: int) -> Outcome | None:
        task = await self._repo.get_task(task_id)
        project = self._project(task)
        if not project.test_command:
            raise RuntimeError(f"{task.project}의 test 명령이 없다")
        run_id = (
            f"t{task.id}-test-{len(await self._repo.list_events(task.id, {EventKind.TEST})) + 1}"
        )
        await self._say(task, "봇이 테스트를 실행한다.", Moment.TEST_RUNNING)
        self._running.tests[task.id] = run_id
        try:
            report = await self._tests.run(run_id, project.test_command, cwd=self._worktree(task))
        finally:
            self._running.tests.pop(task.id, None)
        if report.status.value == "cancelled":
            return None  # /stop
        message_id = await self._say(task, render_test_report(report), Moment.TEST_RESULT)
        record = NewEvent(Actor.BOT, EventKind.TEST, report.to_payload(), message_id)
        detail = report.errors[0] if report.errors else ""
        return TestsFinished(report.passed, report.environment_error, detail), record

    # PR (운영 규약 1.9, 4.5)

    async def _pr_body(self, task: TaskRecord) -> str:
        return render_pr_body(
            decision=await self._decision(task.id),
            summary=await self._summary(task.id),
            report=await self._latest_report(task.id),
            tests=await self._latest_tests(task.id),
            reviews=await self._reviews(task.id),
            discord_url=self._thread_url(task.discord_thread),
            branch=task.branch,
            issue=task.issue_number,
        )

    async def _publish_pr(self, task_id: int) -> Outcome | None:
        task = await self._repo.get_task(task_id)
        github = self._github(task)
        body = await self._pr_body(task)
        if task.pr_number is not None:
            await github.edit_pr_body(task.pr_number, body)
            return None
        summary = await self._summary(task_id)
        number = await github.create_pr(
            base=self._project(task).base_branch,
            head=task.branch,
            title=summary.conventional_title,
            body=body,
        )
        task = await self._repo.update_fields(task.id, {"pr_number": number})
        await github.add_labels(number, ["zerosync", TYPE_LABELS[summary.change_type]])
        await self._say(task, f"draft PR #{number}을 열었다: {self._web(task, f'pull/{number}')}")
        return None

    # 리뷰 (운영 규약 2.3)

    async def _review(self, task_id: int) -> Outcome:
        task = await self._repo.get_task(task_id)
        summary = await self._summary(task_id)
        reviews = await self._reviews(task_id)
        round_ = len(reviews) + 1
        diff = await self._git.diff(self._worktree(task), self._project(task).base_branch)
        if len(diff) > MAX_DIFF_CHARS:
            diff = diff[:MAX_DIFF_CHARS] + "\n... (diff가 길어 잘랐다. 나머지는 저장소에서 읽는다)"
        tests = await self._latest_tests(task_id)
        previous = ""
        if reviews and reviews[-1].review.required_findings:
            previous = render_findings(reviews[-1].review.required_findings)
        agent = self._org.roles.review
        prompt = review_prompt(
            persona_for(self._org, agent),
            author=self._name(self._org.roles.implement),
            title=task.title,
            decision=await self._decision(task_id),
            issue=task.issue_number,
            round_=round_,
            summary=summary,
            tests=render_test_report(tests) if tests else "테스트 결과 없음",
            diff=diff,
            previous_required=previous,
        )
        name = self._name(agent)
        await self._say(task, f"{name}이 리뷰 {round_}라운드를 시작한다.", Moment.REVIEW_RUNNING)
        answer = await self._ask(
            task, agent, Stage.REVIEW, prompt, model=Review, cwd=self._worktree(task)
        )
        if answer.result is None:
            return await self._failed(task, "리뷰", answer)
        review: Review = answer.result
        text = render_review(review, round_=round_)
        message_id = await self._chat.post(
            task.discord_thread,
            agent,
            text,
            mention=should_mention(Moment.REVIEW_ROUND_RESULT),
        )
        if task.pr_number is not None:
            await self._github(task).comment_pr(task.pr_number, f"### {name}\n\n{text}")
        payload = {"review": review.model_dump(mode="json"), "round": round_}
        approved = review.verdict.value == "APPROVED"
        return ReviewFinished(approved), NewEvent(agent, EventKind.REVIEW, payload, message_id)

    async def _mark_ready(self, task: TaskRecord) -> None:
        github = self._github(task)
        await github.edit_pr_body(task.pr_number, await self._pr_body(task))
        await github.mark_ready(task.pr_number)
        reviews = await self._reviews(task.id)
        remaining = len(reviews[-1].review.recommended_findings) if reviews else 0
        hint = " merge 전에 `/fix`로 1회 반영할 수 있다." if remaining else ""
        await self._say(
            task,
            f"{self._name(self._org.roles.review)}이 APPROVED를 냈다. "
            f"PR #{task.pr_number}을 확인하고 merge한다: "
            f"{self._web(task, f'pull/{task.pr_number}')}\n남은 [권장] {remaining}개.{hint}",
            Moment.FINAL_APPROVAL,
        )

    # NEEDS_HUMAN, merge, 중지

    async def _label_needs_human(self, task: TaskRecord, *, add: bool) -> None:
        github = self._project(task).github
        if github is None:
            return
        for number in (task.issue_number, task.pr_number):
            if number is None:
                continue
            if add:
                await github.add_labels(number, ["needs-human"])
            else:
                await github.remove_label(number, "needs-human")

    async def _mark_needs_human(self, task_id: int, reason: str) -> None:
        task = await self._repo.get_task(task_id)
        await self._say(task, render_notice(NoticeCode.NEEDS_HUMAN, reason), Moment.NEEDS_HUMAN)
        await self._side_effect(task_id, lambda t: self._label_needs_human(t, add=True))

    async def _finish_merged(self, task: TaskRecord) -> None:
        """merge 감지 (4.6). 문서 반영(DOC_SYNC)은 Phase 3이라 여기서 끝낸다."""
        github = self._github(task)
        if task.issue_number is not None:
            await github.close_issue(
                task.issue_number,
                not_planned=False,
                comment=f"develop merge 완료 (PR #{task.pr_number}). ZeroSync가 Issue를 닫는다.",
            )
        await self._remove_worktree(task)
        await self._say(
            task,
            f"PR #{task.pr_number} merge를 확인하고 Issue #{task.issue_number}을 닫았다. "
            "작업을 마친다. (문서 반영은 Phase 3에서 한다)",
        )

    async def _cleanup_stopped(self, task: TaskRecord) -> None:
        """/stop (1.8, 3.3).

        Issue는 not planned로 닫고, PR이 있으면 닫고, 없으면 원격 작업 브랜치를 지운다.
        """
        github = self._project(task).github
        if github is not None and task.issue_number is not None:
            await github.close_issue(
                task.issue_number, not_planned=True, comment="Zero가 /stop으로 작업을 중지했다."
            )
        if github is not None and task.pr_number is not None:
            await github.close_pr(task.pr_number, "Zero가 /stop으로 작업을 중지했다.")
        elif task.branch is not None and task.worktree is not None:
            await self._git.delete_remote_branch(
                Path(task.worktree), task.branch, recorded=task.branch
            )
        await self._remove_worktree(task)

    async def _remove_worktree(self, task: TaskRecord) -> None:
        if task.worktree is not None and self._git is not None:
            await self._git.remove_worktree(self._project(task).repo, Path(task.worktree))

    async def poll_merges(self) -> None:
        """AWAIT_MERGE 작업의 PR 상태를 조회해 merge를 감지한다 (SPEC 6.2)."""
        from bot.workflow.state import PrMerged, TaskState

        for task in await self._repo.list_tasks({TaskState.AWAIT_MERGE}):
            if task.pr_number is None or self._project(task).github is None:
                continue
            try:
                state = await self._github(task).pr_state(task.pr_number)
            except Exception as error:
                log.warning("PR 상태 조회 실패 %s: %s", task.pr_number, error)
                continue
            if state.merged:
                record = NewEvent(Actor.BOT, EventKind.MERGE, {"pr": task.pr_number})
                await self._advance(task.id, PrMerged(), record)

    async def prepare_github(self) -> None:
        """라벨이 없으면 만든다 (4.8). 실패해도 봇은 계속 뜬다."""
        for key, project in self._projects.items():
            if project.github is None:
                continue
            try:
                await project.github.ensure_labels()
            except Exception as error:
                await self._chat.notify_ops(
                    f"[{key}] GitHub 라벨 준비 실패: {error}",
                    mention=should_mention(Moment.BOT_ERROR),
                )
