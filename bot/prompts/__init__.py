"""단계별 프롬프트 (SPEC 5.3).

템플릿은 같은 폴더의 `<단계>.md`에 두고 `string.Template`(`$이름`)으로 채운다.
렌더링은 순수 함수이고, 결과는 스냅샷 테스트로 고정한다.
구성: 인격과 관점(운영 규약 1.2, 1.4) → 작업 맥락 → 단계별 지시 → 출력 스키마 → 금지 사항
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from string import Template

from bot.agents.base import AgentName
from bot.schemas import Opinion

PROMPTS_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Persona:
    name: str
    perspective: str
    basic_question: str


PERSONAS: dict[AgentName, Persona] = {
    "claude": Persona(
        "Beta · Claude (ISFJ)",
        "설계, 장기 유지보수, 기존 코드와의 일관성, 사용자 경험",
        "어떻게 하면 제대로 만들 수 있나",
    ),
    "codex": Persona(
        "Alpha · Codex (INTJ)",
        "구현 난이도, 성능, 엣지 케이스, 반례, 더 단순한 대안",
        "왜 실패할 수 있나, 더 작게 할 수 있나",
    ),
}

DISPLAY_NAMES: dict[str, str] = {
    "zero": "Zero",
    "claude": "Beta · Claude",
    "codex": "Alpha · Codex",
    "bot": "ZeroSync",
}


@dataclass(frozen=True)
class HistoryEntry:
    """게시글 흐름의 한 줄. speaker는 zero, claude, codex, bot 중 하나."""

    speaker: str
    text: str


@cache
def _template(name: str) -> Template:
    return Template((PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8"))


def _schema() -> str:
    return json.dumps(Opinion.model_json_schema(), ensure_ascii=False)


def _history(entries: Sequence[HistoryEntry]) -> str:
    if not entries:
        return ""
    lines = ["", "## 지금까지의 흐름", ""]
    for entry in entries:
        lines.append(f"[{DISPLAY_NAMES.get(entry.speaker, entry.speaker)}]")
        lines.append(entry.text.strip())
        lines.append("")
    return "\n".join(lines)


def _common(agent: AgentName, title: str, post: str) -> dict[str, str]:
    persona = PERSONAS[agent]
    return {
        "persona": persona.name,
        "perspective": persona.perspective,
        "basic_question": persona.basic_question,
        "title": title.strip(),
        "post": post.strip(),
        "schema": _schema(),
    }


def opinion_prompt(
    agent: AgentName,
    *,
    title: str,
    post: str,
    question: str = "",
    history: Sequence[HistoryEntry] = (),
) -> str:
    """의견 프롬프트.

    history가 비면 첫 의견: 상대 의견을 보지 않고 독립 작성한다 (운영 규약 1.6).
    """
    if history:
        request = (
            f"지금까지의 흐름을 참고해 Zero의 질문에 답한다.\n\nZero의 질문:\n{question.strip()}"
        )
    else:
        request = (
            "게시글의 아이디어에 대한 너의 의견을 독립적으로 작성한다. "
            "다른 에이전트의 의견은 아직 없으며 참고하지 않는다."
        )
    return _template("opinion").substitute(
        _common(agent, title, post), history=_history(history), request=request
    )


def debate_prompt(
    agent: AgentName,
    *,
    title: str,
    post: str,
    own: str,
    other_agent: AgentName,
    other: str,
    history: Sequence[HistoryEntry] = (),
) -> str:
    """반박 프롬프트. own·other는 렌더링된 직전 의견 전문이다."""
    return _template("debate").substitute(
        _common(agent, title, post),
        history=_history(history),
        own=own.strip(),
        other=other.strip(),
        other_name=DISPLAY_NAMES[other_agent],
    )


def with_format_error(prompt: str, error: str) -> str:
    """형식 오류 재요청 프롬프트 (운영 규약 2.1). 원래 프롬프트에 오류 내용을 붙인다."""
    return (
        f"{prompt.rstrip()}\n\n"
        "## 이전 출력의 형식 오류\n\n"
        f"{error.strip()}\n\n"
        "위 오류를 고쳐 스키마에 맞는 JSON 객체 하나만 다시 출력한다.\n"
    )
