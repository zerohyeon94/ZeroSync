"""교육 Daily의 결정론적 규칙 (ADR-009, 볼트 AGENTS.md "아침").

볼트 파일을 읽고 오늘 할 것 1개를 정한다. 개념 노트 본문만 교육팀장이 쓰고,
나머지(최근 Daily 체크 읽기, 대기열에서 고르기, Daily 만들기, 완료 개수, 대기열 표시)는 여기서 한다.
파일을 읽고 쓰는 일과 계획 계산을 나눠 계산은 순수 함수로 두고 단위 테스트로 고정한다.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from bot.education.note import Question, parse_questions

DAILY_DIR = "Daily"
NOTE_DIR = "Learning/개념"
QUEUE_FILE = "Schedule/학습 대기열.md"
GOALS_GLOB = "Schedule/월별 목표*.md"
TODAY_HEADING = "## 오늘 할 것"
OPTIONAL_HEADING = "## 여유 있으면"
REVIEW_HEADING = "## 복습"
# 복습할 노트: 이 날수 이상 지난 노트 중 가장 최근 것 (간격 두고 다시 꺼내 보기)
REVIEW_DAYS = (3, 7)
NOTE_MINUTES = "20~30분"
WEEKDAYS = "월화수목금토일"

_DAILY_NAME = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")
_NOTE_NAME = re.compile(r"^(\d{4})-(\d{2})-(\d{2}) (.+)\.md$")
_CHECK = re.compile(r"^- \[([ xX])\] (.*)$")
_LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_QUEUE_LINK = re.compile(r"\s*→\s*\[\[[^\]]+\]\]\s*$")
_GOAL_ROW = re.compile(r"^\|\s*(\d{4}-\d{2})\s*\|([^|]*)\|([^|]*)\|([^|]*)\|")
_UNSAFE = re.compile(r'[\\/:*?"<>|#^\[\]]')


class DailyError(ValueError):
    """볼트 파일이 Daily 운영 방식과 맞지 않는다. Zero가 볼트에서 고쳐야 한다."""


@dataclass(frozen=True)
class TodayItem:
    """Daily의 `오늘 할 것` 한 줄."""

    target: str  # 링크 대상 (Learning/개념/2026-11-01 주제)
    label: str
    done: bool


@dataclass(frozen=True)
class QueueItem:
    line: int  # 대기열 파일의 줄 번호 (0부터)
    text: str  # 링크를 뺀 항목 문구
    done: bool
    target: str | None  # 붙어 있는 개념 노트 링크
    section: str = ""  # 속한 `###` 구성 요소 (예: 장비 안)

    @property
    def title(self) -> str:
        """`주제: 설명`에서 주제. 개념 노트 제목과 파일 이름에 쓴다."""
        return self.text.split(":", 1)[0].strip()


@dataclass(frozen=True)
class Month:
    key: str  # 2026-11
    topic: str  # 괄호 설명을 뺀 주제
    certificate: str  # 자격증 칸. 없으면 ""


@dataclass(frozen=True)
class NoteFile:
    day: date  # 파일 이름의 날짜 (노트를 만든 날)
    target: str  # Learning/개념/2026-11-01 주제
    text: str

    @property
    def label(self) -> str:
        return self.target.rsplit("/", 1)[-1][len("YYYY-MM-DD ") :]


@dataclass(frozen=True)
class Review:
    """Daily에 넣는 복습 1문제. 이월하지 않는다."""

    target: str
    label: str
    days_ago: int
    question: Question


@dataclass(frozen=True)
class DailyPlan:
    day: date
    target: str  # 오늘 개념 노트 링크 대상
    label: str
    carried: bool  # 어제 것을 다시 넣는가 (새 노트를 만들지 않는다)
    item: QueueItem | None  # 새로 꺼낸 대기열 항목. 이어 하기면 None
    month: Month
    done_this_month: int
    finished: str | None  # 최근 Daily에서 완료된 노트 링크 (대기열에 [x]로 옮긴다)

    @property
    def note_path(self) -> str:
        return f"{self.target}.md"

    @property
    def daily_path(self) -> str:
        return daily_path(self.day)


def daily_path(day: date) -> str:
    return f"{DAILY_DIR}/{day:%Y-%m}/{day.isoformat()}.md"


def note_target(day: date, title: str) -> str:
    name = re.sub(r"\s+", " ", _UNSAFE.sub(" ", title)).strip()
    if not name:
        raise DailyError("대기열 항목의 주제가 비어 있다")
    return f"{NOTE_DIR}/{day.isoformat()} {name}"


# 읽기


def parse_today(text: str) -> TodayItem | None:
    """`## 오늘 할 것` 섹션의 첫 체크 항목. 섹션이 없으면 예전 형식 Daily로 보고 None."""
    section = _section(text, TODAY_HEADING)
    if section is None:
        return None
    for line in section:
        match = _CHECK.match(line.strip())
        if match is None:
            continue
        link = _LINK.search(match.group(2))
        if link is None:
            return None
        target = link.group(1).strip()
        label = (link.group(2) or target.rsplit("/", 1)[-1]).strip()
        return TodayItem(target, label, match.group(1) != " ")
    return None


def parse_queue(text: str) -> list[QueueItem]:
    items = []
    section = ""
    for number, line in enumerate(text.splitlines()):
        if line.startswith("## "):
            section = ""
        elif line.startswith("### "):
            section = re.sub(r"^\d+\.\s*", "", line[4:]).strip()
        match = _CHECK.match(line.strip())
        if match is None:
            continue
        body = match.group(2)
        link = _LINK.search(body) if _QUEUE_LINK.search(body) else None
        items.append(
            QueueItem(
                line=number,
                text=_QUEUE_LINK.sub("", body).strip(),
                done=match.group(1) != " ",
                target=link.group(1).strip() if link else None,
                section=section,
            )
        )
    return items


def parse_month(goals: str, key: str) -> Month:
    """월별 목표 `한눈에 보기` 표에서 그 달의 주제와 자격증 칸.

    표가 시작되기 전 달(예: 계획이 11월부터인데 10월)이면 가장 가까운 다음 달을 쓴다.
    """
    rows = []
    for line in goals.splitlines():
        match = _GOAL_ROW.match(line.strip())
        if match:
            topic = re.sub(r"\s*\(.*\)\s*$", "", match.group(2)).strip()
            certificate = match.group(4).replace("*", "").strip()
            rows.append(
                Month(match.group(1), topic, "" if certificate in ("", "—", "-") else certificate)
            )
    for month in sorted(rows, key=lambda m: m.key):
        if month.key >= key:
            return month
    raise DailyError(f"월별 목표 표에 {key} 이후의 달이 없다")


def month_criteria(goals: str, key: str) -> list[tuple[str, bool]]:
    """`## YYYY-MM · 주제` 절의 완료 기준 체크 항목 (월말 확인)."""
    lines = _section(goals, f"## {key}", prefix=True) or []
    found = []
    for line in lines:
        match = _CHECK.match(line.strip())
        if match:
            found.append((match.group(2).strip(), match.group(1) != " "))
    return found


def _section(text: str, heading: str, *, prefix: bool = False) -> list[str] | None:
    lines = text.splitlines()
    for start, line in enumerate(lines):
        head = line.strip()
        if head == heading or (prefix and head.startswith(heading)):
            body = []
            for rest in lines[start + 1 :]:
                if rest.startswith("## "):
                    break
                body.append(rest)
            return body
    return None


# 계획


def plan_daily(
    day: date,
    latest: TodayItem | None,
    queue: list[QueueItem],
    month: Month,
    done_this_month: int,
) -> DailyPlan:
    """볼트 AGENTS.md 아침 규칙 2·4·5.

    최근 Daily가 미완료면 같은 링크를 다시 넣고,
    완료였거나 없으면 대기열 맨 위의 미완료 항목을 꺼낸다.
    """
    if latest is not None and not latest.done:
        return DailyPlan(
            day=day,
            target=latest.target,
            label=latest.label,
            carried=True,
            item=None,
            month=month,
            done_this_month=done_this_month,
            finished=None,
        )
    finished = latest.target if latest is not None else None
    remaining = [q for q in queue if not q.done and (finished is None or q.target != finished)]
    if not remaining:
        raise DailyError("학습 대기열에 남은 항목이 없다")
    item = remaining[0]
    # 이미 링크가 붙은 항목(노트를 만든 뒤 Daily가 없어진 경우)은 그 노트를 다시 쓴다
    return DailyPlan(
        day=day,
        target=item.target or note_target(day, item.title),
        label=item.title,
        carried=False,
        item=item,
        month=month,
        done_this_month=done_this_month,
        finished=finished,
    )


def count_done(dailies: list[str]) -> int:
    return sum(1 for text in dailies if (item := parse_today(text)) is not None and item.done)


def optional_for(month: Month, section: str) -> str:
    """선택 1개 (아침 규칙 3). 자격증 준비 달은 기출·요약, 그 외는 오늘 개념의 구성 요소 지도 칸."""
    if month.certificate:
        name = re.sub(r"\s*(준비|응시)\s*$", "", month.certificate).strip()
        return f"{name} 기출·요약 10~15분"
    if section:
        return f"플랫폼 지도: '{section}' 구성 요소 칸 하나 채우기 (5분)"
    return "플랫폼 지도: 오늘 개념과 관련된 구성 요소 칸 하나 채우기 (5분)"


def pick_review(day: date, notes: list[NoteFile], exclude: str) -> Review | None:
    """3일·7일 이상 지난 노트 중 가장 최근 것에서 확인 문제 하나를 고른다.

    노트와 문제는 날짜로 돌려 가며 고른다. 오늘 할 노트(exclude)는 고르지 않는다.
    """
    chosen: list[NoteFile] = []
    for gap in REVIEW_DAYS:
        older = [n for n in notes if n.day <= day - timedelta(days=gap) and n.target != exclude]
        if older and older[-1] not in chosen:
            chosen.append(older[-1])
    if not chosen:
        return None
    note = chosen[day.toordinal() % len(chosen)]
    questions = parse_questions(note.text)
    if not questions:
        return None
    question = questions[day.toordinal() % len(questions)]
    return Review(note.target, note.label, (day - note.day).days, question)


def section_of(queue: list[QueueItem], plan: DailyPlan) -> str:
    if plan.item is not None:
        return plan.item.section
    for item in queue:
        if item.target == plan.target:
            return item.section
    return ""


# 쓰기


def render_daily(
    plan: DailyPlan, goals_link: str, optional: str, review: Review | None = None
) -> str:
    weekday = WEEKDAYS[plan.day.weekday()]
    lines = [
        f"# {plan.day.isoformat()} ({weekday})",
        "",
        f"> [[{goals_link}|이번 달]]: {plan.month.topic} · 이번 달 완료 {plan.done_this_month}개",
        "",
        TODAY_HEADING,
        "",
        f"- [ ] [[{plan.target}|{plan.label}]] — {NOTE_MINUTES}",
    ]
    if review is not None:
        question = review.question
        lines += [
            "",
            REVIEW_HEADING,
            "",
            f"> [[{review.target}|{review.label}]] {question.number}번 · "
            f"{review.days_ago}일 전 개념 · 2분",
            "",
            f"**{question.prompt}**",
            "",
            question.body,
        ]
    if optional.strip():
        lines += ["", OPTIONAL_HEADING, "", f"- [ ] {optional.strip()}"]
    return "\n".join(lines) + "\n"


def note_header(plan: DailyPlan) -> str:
    return (
        f"# {plan.label}\n\n"
        f"> Daily: [[{plan.day.isoformat()}]] · 이번 달 주제: {plan.month.topic} · "
        f"예상 {NOTE_MINUTES}\n\n"
    )


def update_queue(text: str, plan: DailyPlan) -> str:
    """완료된 항목을 [x]로, 오늘 꺼낸 항목에 개념 노트 링크를 붙인다. 다른 줄은 그대로 둔다."""
    lines = text.split("\n")
    items = parse_queue(text)
    if plan.finished is not None:
        for item in items:
            if item.target == plan.finished and not item.done:
                lines[item.line] = lines[item.line].replace("- [ ]", "- [x]", 1)
    if plan.item is not None and plan.item.target is None:
        line = lines[plan.item.line].rstrip()
        lines[plan.item.line] = f"{line} → [[{plan.target}|{plan.label}]]"
    return "\n".join(lines)


# 볼트 읽기


def goals_file(root: Path) -> Path:
    found = sorted(root.glob(GOALS_GLOB))
    if not found:
        raise DailyError("Schedule에 월별 목표 파일이 없다")
    return found[-1]


def note_files(root: Path, before: date) -> list[NoteFile]:
    """`Learning/개념/YYYY-MM-DD 주제.md` 중 before보다 앞선 날짜, 날짜 순."""
    found = []
    for path in (root / NOTE_DIR).glob("*.md"):
        match = _NOTE_NAME.match(path.name)
        if match is None:
            continue
        day = date(*(int(part) for part in match.groups()[:3]))
        if day < before:
            target = f"{NOTE_DIR}/{path.stem}"
            found.append(NoteFile(day, target, path.read_text(encoding="utf-8")))
    return sorted(found, key=lambda n: (n.day, n.target))


def daily_files(root: Path, before: date) -> list[tuple[date, Path]]:
    """`Daily/YYYY-MM/YYYY-MM-DD.md` 중 before보다 앞선 날짜, 날짜 순."""
    found = []
    for path in (root / DAILY_DIR).glob("*/*.md"):
        match = _DAILY_NAME.match(path.name)
        if match is None:
            continue
        day = date(*(int(part) for part in match.groups()))
        if day < before:
            found.append((day, path))
    return sorted(found)
