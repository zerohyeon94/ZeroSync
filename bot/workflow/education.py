"""교육 부서: 매일 아침 Daily와 개념 노트, 일요일 주간 보고와 주간 문제 (ADR-009).

오늘 할 것을 정하는 규칙은 bot.education.daily가, 개념 노트 본문은 교육팀장이 맡는다.
볼트에 파일을 쓰고 커밋하는 주체는 봇이다. 체크박스는 Zero만 체크한다.
매달 1일에는 지난달 사실(완료 개수, 완료 기준)을 함께 알린다. 다음 달 주제는 Zero가 정한다.
주간 보고의 숫자는 bot.education.weekly가 세고, 교육팀장은 주간 문제와 한마디만 쓴다.
문제는 Discord 버튼으로 풀고, 처음 고른 답만 DB에 남겨 다음 주 보고에 넣는다.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from bot.agents.base import AgentName, Stage
from bot.clock import Clock
from bot.education.daily import (
    QUEUE_FILE,
    DailyError,
    DailyPlan,
    Review,
    count_done,
    daily_files,
    daily_path,
    goals_file,
    month_criteria,
    note_files,
    note_header,
    optional_for,
    parse_month,
    parse_queue,
    parse_today,
    pick_review,
    plan_daily,
    render_daily,
    section_of,
    update_queue,
)
from bot.education.note import check_note, complete_note
from bot.education.weekly import (
    QuizScore,
    WeekFacts,
    answer_text,
    check_review,
    render_weekly,
    week_facts,
    week_key,
    week_start,
)
from bot.prompts import concept_note_prompt, weekly_quiz_prompt
from bot.schemas import ConceptNote, QuizQuestion, WeeklyReview

log = logging.getLogger(__name__)

SCOPE = "education"  # 실행 기록의 project 값
COMMIT_TRAILER = "ZeroSync-Department: education"

Notify = Callable[[str, bool], Awaitable[None]]
# 주간 문제를 버튼과 함께 게시한다 (quiz_id, 문제). Discord 계층이 맡는다
PostQuiz = Callable[[int, list[QuizQuestion]], Awaitable[None]]


@dataclass(frozen=True)
class DailyResult:
    created: bool
    text: str  # #교육에 올린 안내


class EducationDesk:
    def __init__(
        self,
        engine: Any,
        vault: Any,
        root: Path,
        agent: AgentName,
        display: str,
        notify: Notify,
        clock: Clock,
        *,
        repo: Any = None,
        post_quiz: PostQuiz | None = None,
    ):
        self._engine = engine
        self._vault = vault
        self._root = root
        self._agent = agent
        self._display = display
        self._notify = notify
        self._clock = clock
        self._repo = repo
        self._post_quiz = post_quiz

    async def run_daily(self) -> DailyResult:
        today = self._clock.now().astimezone().date()
        notes = []
        if today.day == 1:
            notes.append(self.month_review(today - timedelta(days=1)))
        try:
            result = await self._daily(today)
        except DailyError as error:
            result = DailyResult(False, f"오늘 Daily를 만들지 못했다: {error}")
        text = "\n\n".join([*notes, result.text])
        await self._notify(text, not result.created or bool(notes))
        return DailyResult(result.created, text)

    async def _daily(self, today: date) -> DailyResult:
        root = self._root
        path = root / daily_path(today)
        if path.exists():
            return DailyResult(False, f"오늘 Daily({today.isoformat()})가 이미 있다.")
        previous = daily_files(root, today)
        latest = parse_today(_read(previous[-1][1])) if previous else None
        this_month = [_read(p) for d, p in previous if d.strftime("%Y-%m") == f"{today:%Y-%m}"]
        goals = goals_file(root)
        month = parse_month(_read(goals), f"{today:%Y-%m}")
        queue_text = _read(root / QUEUE_FILE)
        queue = parse_queue(queue_text)
        plan = plan_daily(today, latest, queue, month, count_done(this_month))

        written = []
        note = root / plan.note_path
        sources: list[str] = []
        unverified: list[str] = []
        if not note.exists():
            answer = await self._write_note(plan)
            if answer is None:
                return DailyResult(False, f"{self._display}가 개념 노트를 쓰지 못했다.")
            _write(note, complete_note(note_header(plan), answer.body))
            written.append(plan.note_path)
            sources, unverified = answer.sources, answer.unverified
        optional = optional_for(month, section_of(queue, plan))
        goals_link = str(goals.relative_to(root).with_suffix(""))
        review = pick_review(today, note_files(root, today), plan.target)
        _write(path, render_daily(plan, goals_link, optional, review))
        written.append(str(path.relative_to(root)))
        updated = update_queue(queue_text, plan)
        if updated != queue_text:
            _write(root / QUEUE_FILE, updated)
            written.append(QUEUE_FILE)
        if self._vault is not None:
            await self._vault.commit(
                root, written, f"docs(daily): {today.isoformat()} {plan.label}", COMMIT_TRAILER
            )
        return DailyResult(True, _announce(plan, optional, review, sources, unverified))

    async def _write_note(self, plan: DailyPlan) -> ConceptNote | None:
        item = plan.item
        assert item is not None or plan.carried

        async def verify(note: ConceptNote) -> list[str]:
            return check_note(note.body)

        answer = await self._engine.ask_outside_task(
            SCOPE,
            self._agent,
            Stage.CONCEPT_NOTE,
            lambda persona: concept_note_prompt(
                persona,
                day=plan.day.isoformat(),
                label=plan.label,
                item=item.text if item is not None else plan.label,
                section=item.section if item is not None else "",
                month=plan.month.topic,
            ),
            model=ConceptNote,
            cwd=self._root,
            verify=verify,
        )
        if answer.result is None:
            log.warning("개념 노트 실패: %s", answer.error or answer.status)
        return answer.result

    async def run_weekly(self) -> str:
        """이번 주 사실을 세고, 개념이 있으면 교육팀장에게 주간 문제를 받아 함께 올린다."""
        today = self._clock.now().astimezone().date()
        root = self._root
        start = week_start(today)
        dailies = [
            (d, _read(p)) for d, p in daily_files(root, today + timedelta(days=1)) if d >= start
        ]
        queue_path = root / QUEUE_FILE
        queue = parse_queue(_read(queue_path)) if queue_path.exists() else []
        facts = week_facts(today, dailies, queue)
        last = await self._score(week_key(today - timedelta(days=7)))
        week = week_key(today)
        review: WeeklyReview | None = None
        tail = ""
        if self._repo is not None and await self._repo.quiz_for_week(week) is not None:
            tail = "이번 주 문제는 이미 냈다."
        elif facts.concepts:
            review = await self._write_review(facts, last)
            if review is None:
                tail = f"{self._display}가 주간 문제를 만들지 못했다."
        text = render_weekly(facts, last, review.comment if review else [], self._display)
        if tail:
            text += f"\n\n{tail}"
        await self._notify(text, tail.endswith("못했다."))
        if review is not None and self._repo is not None:
            payload = json.dumps([q.model_dump() for q in review.questions], ensure_ascii=False)
            quiz_id = await self._repo.add_quiz(week, payload)
            if self._post_quiz is not None:
                await self._post_quiz(quiz_id, list(review.questions))
        return text

    async def answer(self, quiz_id: int, number: int, choice: str) -> str:
        """Zero가 누른 버튼. 결과와 해설을 돌려준다 (Zero에게만 보인다)."""
        assert self._repo is not None
        stored = await self._repo.get_quiz(quiz_id)
        questions = _questions(stored[1]) if stored is not None else []
        if not 1 <= number <= len(questions):
            return "없는 문제다."
        question = questions[number - 1]
        first = await self._repo.record_quiz_answer(
            quiz_id, number, choice, choice == question.answer
        )
        answered, correct = await self._repo.quiz_score(quiz_id)
        return (
            f"{answer_text(question, choice, first)}\n"
            f"-# 이번 주 {len(questions)}문제 중 {answered}개 풂, {correct}개 맞힘"
        )

    async def _score(self, week: str) -> QuizScore | None:
        if self._repo is None:
            return None
        quiz_id = await self._repo.quiz_for_week(week)
        if quiz_id is None:
            return None
        stored = await self._repo.get_quiz(quiz_id)
        total = len(_questions(stored[1])) if stored is not None else 0
        answered, correct = await self._repo.quiz_score(quiz_id)
        return QuizScore(total, answered, correct)

    async def _write_review(self, facts: WeekFacts, last: QuizScore | None) -> WeeklyReview | None:
        summary = render_weekly(facts, last, [], self._display)

        async def verify(review: WeeklyReview) -> list[str]:
            return check_review(review)

        answer = await self._engine.ask_outside_task(
            SCOPE,
            self._agent,
            Stage.WEEKLY_QUIZ,
            lambda persona: weekly_quiz_prompt(
                persona, facts=summary, notes=[c.target for c in facts.concepts]
            ),
            model=WeeklyReview,
            cwd=self._root,
            verify=verify,
        )
        if answer.result is None:
            log.warning("주간 문제 실패: %s", answer.error or answer.status)
        return answer.result

    def month_review(self, last_day: date) -> str:
        """지난달 사실만 정리한다 (볼트 AGENTS.md "월말" 1·2). 다음 달 주제는 Zero가 정한다."""
        key = f"{last_day:%Y-%m}"
        dailies = [
            _read(p)
            for d, p in daily_files(self._root, last_day + timedelta(days=1))
            if (d.year, d.month) == (last_day.year, last_day.month)
        ]
        try:
            criteria = month_criteria(_read(goals_file(self._root)), key)
        except DailyError:
            criteria = []
        lines = [f"**{key} 월말 확인**", f"- 완료한 개념: {count_done(dailies)}개"]
        if criteria:
            done = [text for text, checked in criteria if checked]
            lines.append(f"- 완료 기준: {len(done)} / {len(criteria)}")
            lines += [f"  - [{'x' if checked else ' '}] {text}" for text, checked in criteria]
        lines.append(
            "다음 달 주제를 유지할지 바꿀지 정해 주세요. "
            "월별 목표의 월말 확인과 다음 달 대기열은 답을 받은 뒤에 채운다."
        )
        return "\n".join(lines)


def _announce(
    plan: DailyPlan,
    optional: str,
    review: Review | None,
    sources: list[str],
    unverified: list[str],
) -> str:
    kind = "어제 것 이어서" if plan.carried else "새 개념"
    lines = [
        f"**오늘 할 것** ({plan.day:%m-%d}, {kind}): {plan.label} — 20~30분",
        f"- 이번 달 {plan.month.topic} · 완료 {plan.done_this_month}개",
    ]
    if review is not None:
        lines.append(
            f"- 복습: {review.label} {review.question.number}번 ({review.days_ago}일 전 개념)"
        )
    lines += [
        f"- 여유 있으면: {optional}",
        f"- Daily: `{plan.daily_path}`",
    ]
    if sources:
        lines.append("- 확인한 자료: " + ", ".join(f"<{url}>" for url in sources))
    if unverified:
        lines.append("- 확인하지 못함: " + "; ".join(unverified))
    return "\n".join(lines)


def _questions(payload: str) -> list[QuizQuestion]:
    return [QuizQuestion.model_validate(item) for item in json.loads(payload)]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
