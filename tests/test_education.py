"""교육 Daily 규칙과 실행 테스트 (ADR-009, 볼트 AGENTS.md "아침").

볼트는 tmp_path에 만들고, 교육팀장 호출과 커밋은 가짜로 바꾼다.
"""

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pytest

from bot.clock import FixedClock
from bot.education.daily import (
    DailyError,
    Month,
    NoteFile,
    QueueItem,
    TodayItem,
    note_target,
    optional_for,
    parse_month,
    parse_queue,
    parse_today,
    pick_review,
    plan_daily,
    render_daily,
    update_queue,
)
from bot.education.note import check_note, parse_questions
from bot.schemas import ConceptNote
from bot.workflow.education import EducationDesk

GOALS = """\
# 월별 목표

| 월 | 주제 | 층 | 자격증 |
|---|---|---|---|
| 2026-11 | 시스템 전체 한 바퀴 (플랫폼 지도) | 폭 | — |
| 2027-02 | 데이터 계층 (PostgreSQL) | 폭 | SQLD 준비 |
| 2027-03 | 실시간·영상 | 폭 | **SQLD 응시** |

## 2026-10 · 준비

- [x] 운영 방식을 정했다
- [ ] 대기열을 채웠다

**월말 확인:**

## 2026-11 · 시스템 전체 한 바퀴 (플랫폼 지도)

- [ ] 16개 구성 요소에 표시했다
"""

QUEUE = """\
# 학습 대기열

## 2026-11 · 시스템 전체 한 바퀴

### 0. 전체
- [ ] 엣지-중앙 서버 구조: 장비와 서버의 역할 나누기

### 1. 장비 안
- [ ] 소리 이벤트 감지 기초: dB, EWMA
- [ ] gRPC 스트리밍: 서버 스트림과 keepalive
"""

BODY = """\
## 한 문장으로

장비는 현장에서 판단하고 서버는 모아서 보여 준다.

## 비유

지점과 본사다. 다만 지점이 본사 없이도 일을 계속한다는 점은 다르다.

## 흐름

```text
장비 → 서버 → 화면
```

## 어디서 깨지나

연결이 끊기면 이벤트가 늦게 도착한다.

## 이런 시스템에서는

엣지 장비가 이벤트를 만들고 중앙 서버가 수집한다.

## 단어 정리

- **엣지:** 현장에 있는 장비

## 확인 문제

### 1. 개념

- [ ] A. 하나
- [ ] B. 둘
- [ ] C. 셋
- [ ] D. 넷

> [!answer]- 정답과 해설
> - 정답: A
> - 해설: 하나다

### 2. 흐름

- [ ] A. 하나
- [ ] B. 둘
- [ ] C. 셋
- [ ] D. 넷

> [!answer]- 정답과 해설
> - 정답: B
> - 해설: 둘이다

### 3. 실패

- [ ] A. 하나
- [ ] B. 둘
- [ ] C. 셋
- [ ] D. 넷

> [!answer]- 정답과 해설
> - 정답: C
> - 해설: 셋이다
"""

NOV = Month("2026-11", "시스템 전체 한 바퀴", "")


def daily_text(target, label, done):
    return (
        f"# x\n\n> 머리말\n\n## 오늘 할 것\n\n- [{'x' if done else ' '}] "
        f"[[{target}|{label}]] — 20~30분\n\n## 여유 있으면\n\n- [ ] 선택\n"
    )


# 읽기


def test_parse_today_reads_first_check_and_link():
    item = parse_today(daily_text("Learning/개념/2026-11-01 엣지", "엣지", done=True))
    assert item == TodayItem("Learning/개념/2026-11-01 엣지", "엣지", True)
    assert parse_today(daily_text("a/b", "b", done=False)).done is False


def test_old_format_daily_counts_as_no_daily():
    assert parse_today("# 2026-09-23\n\n## ✅ 오늘 수행 목록\n\n- [x] Mobile\n") is None


def test_parse_queue_keeps_sections_links_and_done():
    text = QUEUE.replace(
        "- [ ] 엣지-중앙 서버 구조: 장비와 서버의 역할 나누기",
        "- [x] 엣지-중앙 서버 구조: 장비와 서버의 역할 나누기 → [[Learning/개념/a 엣지|엣지]]",
    )
    items = parse_queue(text)
    assert [(i.title, i.done, i.target, i.section) for i in items] == [
        ("엣지-중앙 서버 구조", True, "Learning/개념/a 엣지", "전체"),
        ("소리 이벤트 감지 기초", False, None, "장비 안"),
        ("gRPC 스트리밍", False, None, "장비 안"),
    ]


def test_parse_month_strips_note_and_reads_certificate():
    assert parse_month(GOALS, "2026-11") == NOV
    assert parse_month(GOALS, "2027-03").certificate == "SQLD 응시"
    assert parse_month(GOALS, "2026-10") == NOV  # 계획 시작 전 달은 다음 달 주제
    with pytest.raises(DailyError):
        parse_month(GOALS, "2030-01")


# 계획


def test_unfinished_daily_is_carried_without_new_note():
    latest = TodayItem("Learning/개념/2026-11-01 엣지", "엣지", False)
    plan = plan_daily(date(2026, 11, 2), latest, parse_queue(QUEUE), NOV, 0)
    assert plan.carried and plan.item is None
    assert plan.target == "Learning/개념/2026-11-01 엣지"


def test_finished_or_missing_daily_takes_top_of_queue():
    queue = parse_queue(QUEUE)
    first = plan_daily(date(2026, 11, 1), None, queue, NOV, 0)
    assert first.label == "엣지-중앙 서버 구조" and first.finished is None
    assert first.target == "Learning/개념/2026-11-01 엣지-중앙 서버 구조"

    linked = parse_queue(update_queue(QUEUE, first))
    latest = TodayItem(first.target, first.label, True)
    second = plan_daily(date(2026, 11, 2), latest, linked, NOV, 1)
    assert second.label == "소리 이벤트 감지 기초"
    assert second.finished == first.target


def test_empty_queue_is_an_error():
    done = QUEUE.replace("- [ ]", "- [x]")
    with pytest.raises(DailyError, match="남은 항목"):
        plan_daily(date(2026, 11, 1), None, parse_queue(done), NOV, 0)


def test_queue_item_with_link_reuses_its_note():
    item = QueueItem(3, "엣지: 설명", False, "Learning/개념/2026-10-31 엣지", "전체")
    plan = plan_daily(date(2026, 11, 1), None, [item], NOV, 0)
    assert plan.target == "Learning/개념/2026-10-31 엣지"


def test_note_names_drop_characters_obsidian_cannot_link():
    assert note_target(date(2026, 11, 1), "SSE와 pull: [방식]") == (
        "Learning/개념/2026-11-01 SSE와 pull 방식"
    )


def test_optional_item_follows_certificate_month_or_section():
    assert optional_for(NOV, "장비 안") == "플랫폼 지도: '장비 안' 구성 요소 칸 하나 채우기 (5분)"
    sqld = Month("2027-02", "데이터 계층", "SQLD 준비")
    assert optional_for(sqld, "서버") == "SQLD 기출·요약 10~15분"


def _note(day, name):
    return NoteFile(day, f"Learning/개념/{day.isoformat()} {name}", BODY)


def test_review_takes_latest_note_at_least_three_or_seven_days_old():
    notes = [
        _note(date(2026, 11, 1), "가"),
        _note(date(2026, 11, 4), "나"),
        _note(date(2026, 11, 6), "다"),
        _note(date(2026, 11, 7), "라"),
    ]
    day = date(2026, 11, 9)  # 3일 전 이하 최근: 11-06 다, 7일 전 이하 최근: 11-01 가
    review = pick_review(day, notes, "")
    assert review.label in ("다", "가")
    assert review.days_ago == (day - date(2026, 11, 6 if review.label == "다" else 1)).days
    labels = {pick_review(date(2026, 11, 9) + timedelta(days=d), notes, "").label for d in (0, 1)}
    assert len(labels) == 2  # 날마다 돌려 가며 고른다


def test_review_skips_todays_note_and_young_notes():
    notes = [_note(date(2026, 11, 1), "가"), _note(date(2026, 11, 3), "나")]
    assert pick_review(date(2026, 11, 3), notes, "") is None  # 3일 지난 노트가 없다
    only = pick_review(date(2026, 11, 4), notes, "Learning/개념/2026-11-01 가")
    assert only is None


def test_review_question_rotates_by_day():
    notes = [_note(date(2026, 11, 1), "가")]
    numbers = {pick_review(date(2026, 11, d), notes, "").question.number for d in (4, 5, 6)}
    assert numbers == {1, 2, 3}


def test_parse_questions_splits_prompt_and_body():
    questions = parse_questions(BODY)
    assert [q.prompt for q in questions] == ["개념", "흐름", "실패"]
    assert questions[1].body.startswith("- [ ] A. 하나") and "> - 정답: B" in questions[1].body


# 쓰기


def test_render_daily_matches_template():
    plan = plan_daily(date(2026, 11, 1), None, parse_queue(QUEUE), NOV, 0)
    text = render_daily(plan, "Schedule/월별 목표 (2026-11 ~ 2027-10)", "플랫폼 지도: 칸")
    assert text == (
        "# 2026-11-01 (일)\n\n"
        "> [[Schedule/월별 목표 (2026-11 ~ 2027-10)|이번 달]]: 시스템 전체 한 바퀴 · "
        "이번 달 완료 0개\n\n"
        "## 오늘 할 것\n\n"
        "- [ ] [[Learning/개념/2026-11-01 엣지-중앙 서버 구조|엣지-중앙 서버 구조]] — 20~30분\n\n"
        "## 여유 있으면\n\n"
        "- [ ] 플랫폼 지도: 칸\n"
    )


def test_render_daily_puts_review_between_today_and_optional():
    plan = plan_daily(date(2026, 11, 5), None, parse_queue(QUEUE), NOV, 0)
    review = pick_review(date(2026, 11, 5), [_note(date(2026, 11, 1), "가")], plan.target)
    text = render_daily(plan, "g", "선택", review)
    today, rest = text.split("## 복습\n\n")
    assert "## 오늘 할 것" in today
    assert rest.startswith(
        f"> [[Learning/개념/2026-11-01 가|가]] {review.question.number}번 · 4일 전 개념 · 2분\n\n"
        f"**{review.question.prompt}**\n\n- [ ] A. 하나"
    )
    assert rest.index("> [!answer]-") < rest.index("## 여유 있으면")


def test_update_queue_marks_done_and_links_today_only():
    first = plan_daily(date(2026, 11, 1), None, parse_queue(QUEUE), NOV, 0)
    once = update_queue(QUEUE, first)
    assert "- [ ] 엣지-중앙 서버 구조: 장비와 서버의 역할 나누기 → [[" in once
    second = plan_daily(
        date(2026, 11, 2), TodayItem(first.target, first.label, True), parse_queue(once), NOV, 1
    )
    twice = update_queue(once, second)
    lines = twice.splitlines()
    assert lines[5].startswith("- [x] 엣지-중앙 서버 구조")
    assert lines[8].startswith("- [ ] 소리 이벤트 감지 기초: dB, EWMA → [[Learning/개념/2026-11-02")
    assert lines[9] == "- [ ] gRPC 스트리밍: 서버 스트림과 keepalive"
    assert twice.endswith("\n")


# 개념 노트 검사


def test_valid_note_has_no_problems():
    assert check_note(BODY) == []


@pytest.mark.parametrize(
    ("body", "problem"),
    [
        ("# 제목\n\n" + BODY, "제목"),
        (BODY.replace("## 비유", "## 예시"), "빠진 섹션: ## 비유"),
        (BODY.split("### 3.")[0], "확인 문제는 3개다"),
        (BODY.replace("- [ ] D. 넷", "", 1), "1번 문제"),
        (BODY.replace("> [!answer]- 정답과 해설\n> - 정답: B", "> 정답: B"), "2번 문제"),
        (BODY + "\n`회사/플랫폼 지도.md` 참고\n", "회사 폴더"),
        (BODY + "\n## 내 말로 한 줄 (선택)\n", "템플릿에 없는 섹션"),
    ],
)
def test_note_problems_are_reported(body, problem):
    assert any(problem in found for found in check_note(body))


# 실행


@dataclass
class FakeAnswer:
    result: ConceptNote | None
    error: str = ""
    status: str = "ok"


class FakeEngine:
    def __init__(self, note=None):
        self.note = note
        self.calls = []

    async def ask_outside_task(self, scope, agent, stage, build_prompt, *, model, cwd, verify):
        prompt = build_prompt(_persona())
        self.calls.append((scope, agent, stage.value, prompt))
        if self.note is None:
            return FakeAnswer(None, "형식 오류")
        assert await verify(self.note) == []
        return FakeAnswer(self.note)


class FakeVault:
    def __init__(self):
        self.commits = []

    async def commit(self, root, paths, title, trailer):
        self.commits.append((list(paths), title))
        return True


def _persona():
    from bot.org import DEFAULT_ORG
    from bot.prompts import persona_for

    return persona_for(DEFAULT_ORG, "eta")


def make_vault(tmp_path):
    (tmp_path / "Schedule").mkdir()
    (tmp_path / "Schedule" / "월별 목표 (2026-11 ~ 2027-10).md").write_text(GOALS, "utf-8")
    (tmp_path / "Schedule" / "학습 대기열.md").write_text(QUEUE, "utf-8")
    return tmp_path


def run_desk(tmp_path, day, engine, vault=None):
    notes = []

    async def notify(text, mention):
        notes.append((text, mention))

    clock = FixedClock(datetime(day.year, day.month, day.day, 7, 30).astimezone())
    desk = EducationDesk(engine, vault, tmp_path, "eta", "Eta · 교육팀장", notify, clock)
    result = asyncio.run(desk.run_daily())
    return result, notes


NOTE = ConceptNote(body=BODY, sources=["https://grpc.io/docs/"])


def test_new_day_writes_note_daily_queue_and_commits(tmp_path):
    root = make_vault(tmp_path)
    engine, vault = FakeEngine(NOTE), FakeVault()
    result, notes = run_desk(root, date(2026, 11, 2), engine, vault)

    assert result.created
    scope, agent, stage, prompt = engine.calls[0]
    assert (scope, agent, stage) == ("education", "eta", "concept_note")
    assert "주제: 엣지-중앙 서버 구조" in prompt and "구성 요소: 전체" in prompt
    note = root / "Learning/개념/2026-11-02 엣지-중앙 서버 구조.md"
    text = note.read_text("utf-8")
    assert text.startswith("# 엣지-중앙 서버 구조\n\n> Daily: [[2026-11-02]] · 이번 달 주제: ")
    assert text.rstrip().endswith("> - 해설: 셋이다") and "내 말로 한 줄" not in text
    daily = (root / "Daily/2026-11/2026-11-02.md").read_text("utf-8")
    assert "# 2026-11-02 (월)" in daily and "플랫폼 지도: '전체'" in daily
    assert "→ [[Learning/개념/2026-11-02 엣지-중앙 서버 구조|" in (
        root / "Schedule/학습 대기열.md"
    ).read_text("utf-8")
    assert vault.commits == [
        (
            [
                "Learning/개념/2026-11-02 엣지-중앙 서버 구조.md",
                "Daily/2026-11/2026-11-02.md",
                "Schedule/학습 대기열.md",
            ],
            "docs(daily): 2026-11-02 엣지-중앙 서버 구조",
        )
    ]
    assert notes[0][1] is False
    assert "새 개념" in notes[0][0] and "<https://grpc.io/docs/>" in notes[0][0]


def test_unfinished_yesterday_is_carried_without_calling_agent(tmp_path):
    root = make_vault(tmp_path)
    run_desk(root, date(2026, 11, 2), FakeEngine(NOTE))
    engine = FakeEngine(NOTE)
    result, notes = run_desk(root, date(2026, 11, 3), engine)
    assert result.created and engine.calls == []
    daily = (root / "Daily/2026-11/2026-11-03.md").read_text("utf-8")
    assert "[[Learning/개념/2026-11-02 엣지-중앙 서버 구조|엣지-중앙 서버 구조]]" in daily
    assert "어제 것 이어서" in notes[0][0]


def test_finished_yesterday_moves_on_and_counts(tmp_path):
    root = make_vault(tmp_path)
    run_desk(root, date(2026, 11, 2), FakeEngine(NOTE))
    path = root / "Daily/2026-11/2026-11-02.md"
    path.write_text(path.read_text("utf-8").replace("- [ ] [[", "- [x] [["), "utf-8")
    run_desk(root, date(2026, 11, 3), FakeEngine(NOTE))
    daily = (root / "Daily/2026-11/2026-11-03.md").read_text("utf-8")
    assert "소리 이벤트 감지 기초" in daily and "이번 달 완료 1개" in daily
    queue = (root / "Schedule/학습 대기열.md").read_text("utf-8")
    assert "- [x] 엣지-중앙 서버 구조" in queue


def test_existing_daily_is_left_alone(tmp_path):
    root = make_vault(tmp_path)
    run_desk(root, date(2026, 11, 2), FakeEngine(NOTE))
    engine = FakeEngine(NOTE)
    result, notes = run_desk(root, date(2026, 11, 2), engine)
    assert not result.created and engine.calls == []
    assert "이미 있다" in notes[0][0]


def test_agent_failure_writes_nothing_and_mentions(tmp_path):
    root = make_vault(tmp_path)
    vault = FakeVault()
    result, notes = run_desk(root, date(2026, 11, 2), FakeEngine(None), vault)
    assert not result.created and vault.commits == []
    assert not (root / "Daily").exists()
    assert notes == [("Eta · 교육팀장가 개념 노트를 쓰지 못했다.", True)]


def test_first_day_of_month_reports_last_month_facts(tmp_path):
    root = make_vault(tmp_path)
    old = root / "Daily/2026-10/2026-10-31.md"
    old.parent.mkdir(parents=True)
    old.write_text(daily_text("Learning/개념/2026-10-31 준비", "준비", done=True), "utf-8")
    result, notes = run_desk(root, date(2026, 11, 1), FakeEngine(NOTE))
    text, mention = notes[0]
    assert mention is True
    assert "**2026-10 월말 확인**" in text and "완료한 개념: 1개" in text
    assert "완료 기준: 1 / 2" in text and "- [x] 운영 방식을 정했다" in text
    assert "오늘 할 것" in text


def test_daily_includes_review_from_older_note(tmp_path):
    root = make_vault(tmp_path)
    run_desk(root, date(2026, 11, 2), FakeEngine(NOTE))
    for day in (2, 3, 4):  # 11-04 노트는 끝내지 않아 11-05에 이어 한다
        path = root / f"Daily/2026-11/2026-11-0{day}.md"
        if day < 4:
            path.write_text(path.read_text("utf-8").replace("- [ ] [[", "- [x] [["), "utf-8")
        run_desk(root, date(2026, 11, day + 1), FakeEngine(NOTE))
    daily = (root / "Daily/2026-11/2026-11-05.md").read_text("utf-8")
    assert "## 복습" in daily and "엣지-중앙 서버 구조|엣지-중앙 서버 구조]]" in daily
    assert "3일 전 개념" in daily
    early = (root / "Daily/2026-11/2026-11-03.md").read_text("utf-8")
    assert "## 복습" not in early
