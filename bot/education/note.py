"""개념 노트 형식 검사 (볼트 Templates/개념 노트.md, AGENTS.md "개념 노트 작성 기준").

교육팀장이 쓴 본문이 템플릿 섹션 순서와 확인 문제 형식을 지키는지 본다. 내용의 사실 여부는
판단하지 않는다(봇은 해석하지 않는다). 문제가 있으면 목록을 돌려주고, 엔진이 1회 다시 요청한다.
"""

import re

SECTIONS = (
    "## 한 문장으로",
    "## 비유",
    "## 흐름",
    "## 어디서 깨지나",
    "## 이런 시스템에서는",
    "## 단어 정리",
    "## 확인 문제",
)
QUESTIONS = 3
OPTIONS = ("A.", "B.", "C.", "D.")
ANSWER = "> [!answer]-"
# 볼트에서 git에 올라가지 않는 회사 폴더. 노트에 경로조차 남기지 않는다
PRIVATE = "회사/"


def check_note(body: str) -> list[str]:
    problems = []
    text = body.strip()
    if text.startswith("# "):
        problems.append("제목(# …)과 머리말은 봇이 붙인다. 본문은 '## 한 문장으로'부터 쓴다")
    headings = [line.strip() for line in text.splitlines() if line.startswith("## ")]
    expected = [h for h in headings if h in SECTIONS]
    if tuple(expected) != SECTIONS:
        missing = [h for h in SECTIONS if h not in headings]
        if missing:
            problems.append(f"빠진 섹션: {', '.join(missing)}")
        else:
            problems.append(f"섹션 순서는 {' → '.join(s[3:] for s in SECTIONS)}이다")
    extra = [h for h in headings if h not in SECTIONS]
    if extra:
        problems.append(f"템플릿에 없는 섹션: {', '.join(extra)}")
    problems += _check_questions(text)
    if PRIVATE in text:
        problems.append("회사 폴더(회사/)의 경로나 내용을 쓰지 않는다")
    return problems


def _check_questions(text: str) -> list[str]:
    start = text.find("## 확인 문제")
    if start < 0:
        return []
    rest = text[start:].split("\n", 1)[1] if "\n" in text[start:] else ""
    end = rest.find("\n## ")
    block = rest if end < 0 else rest[:end]
    parts = re.split(r"^### ", block, flags=re.MULTILINE)[1:]
    if len(parts) != QUESTIONS:
        return [f"확인 문제는 {QUESTIONS}개다 (지금 {len(parts)}개)"]
    problems = []
    for number, part in enumerate(parts, start=1):
        lines = [line.strip() for line in part.splitlines()]
        options = [line for line in lines if line.startswith("- [ ] ")]
        labels = tuple(line[6:].split(" ", 1)[0] for line in options)
        if labels != OPTIONS:
            problems.append(f"{number}번 문제는 '- [ ] A.' ~ '- [ ] D.' 4지선다다")
        if not any(line.startswith(ANSWER) for line in lines):
            problems.append(f"{number}번 문제에 접힌 정답 callout({ANSWER} 정답과 해설)이 없다")
    return problems


def complete_note(header: str, body: str) -> str:
    """봇이 정한 제목·머리말을 붙인다."""
    return header + body.strip() + "\n"
