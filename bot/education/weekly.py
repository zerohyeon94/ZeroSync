"""교육 주간 보고의 결정론적 규칙 (ADR-009).

이번 주(월~오늘) Daily와 학습 대기열에서 사실만 센다. 다음 주를 위한 한마디와
주간 문제는 교육팀장이 쓰고, 숫자와 목록은 여기서 만든다.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from bot.education.daily import QueueItem, parse_today
from bot.education.note import PRIVATE
from bot.schemas import LETTERS, QuizQuestion, WeeklyReview


@dataclass(frozen=True)
class WeekConcept:
    target: str
    label: str
    done: bool


@dataclass(frozen=True)
class WeekFacts:
    start: date  # 이번 주 월요일
    end: date  # 보고하는 날
    daily_days: int  # Daily를 만든 날 수
    concepts: list[WeekConcept]  # 이번 주에 다룬 개념, 처음 나온 순서
    month: str
    month_done: int  # 이번 달 대기열에서 끝낸 항목
    month_total: int

    @property
    def done(self) -> int:
        return sum(1 for concept in self.concepts if concept.done)


@dataclass(frozen=True)
class QuizScore:
    total: int
    answered: int
    correct: int


def week_key(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def week_facts(day: date, dailies: list[tuple[date, str]], queue: list[QueueItem]) -> WeekFacts:
    """dailies는 (날짜, Daily 본문). 이번 주 월요일~day만 센다."""
    start = week_start(day)
    concepts: dict[str, WeekConcept] = {}
    days = 0
    for when, text in sorted(dailies):
        if not start <= when <= day:
            continue
        days += 1
        item = parse_today(text)
        if item is None:
            continue
        seen = concepts.get(item.target)
        concepts[item.target] = WeekConcept(
            item.target, item.label, item.done or (seen is not None and seen.done)
        )
    month = f"{day:%Y-%m}"
    items = [q for q in queue if q.month == month]
    return WeekFacts(
        start=start,
        end=day,
        daily_days=days,
        concepts=list(concepts.values()),
        month=month,
        month_done=sum(1 for q in items if q.done),
        month_total=len(items),
    )


def render_weekly(
    facts: WeekFacts, last_quiz: QuizScore | None, comment: list[str], display: str
) -> str:
    total_days = (facts.end - facts.start).days + 1
    lines = [
        f"**주간 학습 보고** ({facts.start:%m-%d} ~ {facts.end:%m-%d})",
        f"- Daily: {total_days}일 중 {facts.daily_days}일 · 끝낸 개념 {facts.done}개",
    ]
    if facts.month_total:
        lines.append(f"- {facts.month} 대기열: {facts.month_total}개 중 {facts.month_done}개 완료")
    if last_quiz is not None:
        if last_quiz.answered:
            lines.append(
                f"- 지난주 문제: {last_quiz.total}문제 중 {last_quiz.answered}개 풂, "
                f"{last_quiz.correct}개 맞힘"
            )
        else:
            lines.append(f"- 지난주 문제: {last_quiz.total}문제, 풀지 않음")
    if facts.concepts:
        lines += ["", "**이번 주 개념**"]
        for concept in facts.concepts:
            state = "x" if concept.done else " "
            rest = "" if concept.done else " (이어 하는 중)"
            lines.append(f"- [{state}] {concept.label}{rest}")
    if comment:
        lines += ["", f"**{display}의 한마디**", *(f"- {line}" for line in comment)]
    return "\n".join(lines)


def render_question(question: QuizQuestion, number: int, total: int) -> str:
    options = [f"{letter}. {text}" for letter, text in zip(LETTERS, question.options, strict=True)]
    return "\n".join([f"**주간 문제 {number}/{total}**", question.prompt, "", *options])


def answer_text(question: QuizQuestion, chosen: str, first: str) -> str:
    """버튼을 누른 Zero에게만 보이는 결과. 처음 고른 답만 점수에 남는다."""
    if chosen != first:
        head = f"이미 {first}를 골랐다 (정답 {question.answer}). 처음 고른 답만 기록한다."
    elif first == question.answer:
        head = f"정답이다 ({question.answer})."
    else:
        head = f"오답이다. 고른 답 {first}, 정답 {question.answer}."
    return f"{head}\n{question.explanation}"


def check_review(review: WeeklyReview) -> list[str]:
    """주간 문제 형식. 내용의 사실 여부는 판단하지 않는다."""
    problems = []
    for number, question in enumerate(review.questions, start=1):
        if len(set(question.options)) != len(question.options):
            problems.append(f"{number}번 문제의 보기가 겹친다")
        marks = {f"{letter}." for letter in LETTERS}
        if any(option[:2] in marks for option in question.options):
            problems.append(f"{number}번 문제의 보기에 'A.' 같은 머리표를 붙이지 않는다")
    texts = [*review.comment]
    for question in review.questions:
        texts += [question.prompt, question.explanation, *question.options]
    if any(PRIVATE in text for text in texts):
        problems.append("회사 폴더(회사/)의 경로나 내용을 쓰지 않는다")
    return problems
