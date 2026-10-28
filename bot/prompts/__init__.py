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

from pydantic import BaseModel

from bot.org import Org
from bot.schemas import DesignSummary, ImplementationReport, Opinion, Review

PROMPTS_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Persona:
    """프롬프트에 넣는 인격. 회사 설정(org.yaml, agents/<이름>.md)에서 만든다 (SPEC 5.3)."""

    name: str  # 예: Beta · 기획팀장 (INFJ)
    perspective: str
    basic_question: str
    profile: str = ""  # 인격 파일 전문 (역량, 위험과 보완)
    rejected: tuple[str, ...] = ()  # Zero가 거절한 이 팀장의 채용 제안 (운영 규약 1.12)


def persona_for(org: Org, agent: str, rejected: Sequence[str] = ()) -> Persona:
    spec = org.agents[agent]
    name = org.display(agent) + (f" ({spec.mbti})" if spec.mbti else "")
    return Persona(name, spec.perspective, spec.basic_question, org.profile(agent), tuple(rejected))


HIRING_GUIDE = (
    "자기 팀 역량 밖의 일이 반복되거나, 다른 관점이나 실제로 일을 맡을 담당이 더 필요하면 "
    "출력의 hiring_proposal에 근거와 함께 새 팀·팀원을 제안한다. 근거가 없으면 null로 둔다. "
    "팀이나 역할을 직접 만들지 않는다. 채용은 Zero가 정한다."
)


@dataclass(frozen=True)
class HistoryEntry:
    """게시글 흐름의 한 줄. speaker는 표시 이름(예: Zero, Beta · 기획팀장)이다."""

    speaker: str
    text: str


@cache
def _template(name: str) -> Template:
    return Template((PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8"))


def _schema(model: type[BaseModel] = Opinion) -> str:
    return json.dumps(model.model_json_schema(), ensure_ascii=False)


def _history(entries: Sequence[HistoryEntry]) -> str:
    if not entries:
        return ""
    lines = ["", "## 지금까지의 흐름", ""]
    for entry in entries:
        lines.append(f"[{entry.speaker}]")
        lines.append(entry.text.strip())
        lines.append("")
    return "\n".join(lines)


def _profile(persona: Persona) -> str:
    parts = []
    if persona.profile.strip():
        parts.append(f"## 인격과 역량\n\n{persona.profile.strip()}")
    hiring = HIRING_GUIDE
    if persona.rejected:
        hiring += "\n\nZero가 거절한 제안 (새 근거 없이 다시 제안하지 않는다):\n" + "\n".join(
            f"- {line}" for line in persona.rejected
        )
    parts.append(f"## 채용 제안\n\n{hiring}")
    return "\n" + "\n\n".join(parts) + "\n\n"


def _common(persona: Persona, title: str, post: str) -> dict[str, str]:
    return {
        "persona": persona.name,
        "perspective": persona.perspective,
        "basic_question": persona.basic_question,
        "profile": _profile(persona),
        "title": title.strip(),
        "post": post.strip(),
        "schema": _schema(),
    }


def opinion_prompt(
    persona: Persona,
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
        _common(persona, title, post), history=_history(history), request=request
    )


def debate_prompt(
    persona: Persona,
    *,
    title: str,
    post: str,
    own: str,
    other_name: str,
    other: str,
    history: Sequence[HistoryEntry] = (),
) -> str:
    """반박 프롬프트. own·other는 렌더링된 직전 의견 전문이다."""
    return _template("debate").substitute(
        _common(persona, title, post),
        history=_history(history),
        own=own.strip(),
        other=other.strip(),
        other_name=other_name,
    )


def with_format_error(prompt: str, error: str) -> str:
    """형식 오류 재요청 프롬프트 (운영 규약 2.1). 원래 프롬프트에 오류 내용을 붙인다."""
    return (
        f"{prompt.rstrip()}\n\n"
        "## 이전 출력의 형식 오류\n\n"
        f"{error.strip()}\n\n"
        "위 오류를 고쳐 스키마에 맞는 JSON 객체 하나만 다시 출력한다.\n"
    )


# Phase 2: 설계, 구현, 수정, 리뷰


def _persona(persona: Persona) -> dict[str, str]:
    return {
        "persona": persona.name,
        "perspective": persona.perspective,
        "profile": _profile(persona),
    }


def _section(title: str, body: str) -> str:
    return f"\n## {title}\n\n{body.strip()}\n" if body.strip() else ""


def design_text(summary: DesignSummary) -> str:
    """프롬프트에 넣는 설계 요약."""
    lines = [
        f"- 변경 유형: {summary.change_type.label} ({summary.change_type.value})",
        f"- 대상 기능: {summary.target_feature}",
        f"- 제목: {summary.conventional_title}",
        f"- 요약: {summary.summary}",
        "- 바꿀 것:",
        *(f"  - {item}" for item in summary.changes),
        "- 테스트 계획:",
        *(f"  - {item}" for item in summary.test_plan),
    ]
    if summary.risks:
        lines += ["- 위험:", *(f"  - {item}" for item in summary.risks)]
    return "\n".join(lines)


def design_prompt(
    persona: Persona,
    *,
    title: str,
    post: str,
    decision: str,
    issue: int,
    features: Sequence[str] | None,
    history: Sequence[HistoryEntry] = (),
    revision: str = "",
    previous: DesignSummary | None = None,
) -> str:
    if features is None:
        feature_text = "(볼트 기능 폴더를 읽지 못했다. 기존 기능이면 그 이름을 그대로 쓴다)"
    else:
        feature_text = "\n".join(f"- {name}" for name in sorted(features)) or "(아직 없다)"
    revision_text = ""
    if revision:
        body = f"Zero의 수정 요청:\n{revision.strip()}\n"
        if previous is not None:
            body += (
                f"\n이전 설계 요약:\n{design_text(previous)}\n\n"
                f"같은 파일(`{previous.design_doc}`)을 고쳐 새 커밋으로 추가한다. "
                "slug나 변경 유형이 바뀌면 파일 이름도 새 slug로 옮긴다"
            )
        revision_text = _section("수정 요청", body)
    return _template("design").substitute(
        _persona(persona),
        title=title.strip(),
        issue=issue,
        post=post.strip(),
        decision=decision.strip(),
        history=_history(history),
        features=feature_text,
        revision=revision_text,
        schema=_schema(DesignSummary),
    )


def implement_prompt(
    persona: Persona, *, title: str, decision: str, issue: int, branch: str, summary: DesignSummary
) -> str:
    return _template("implement").substitute(
        _persona(persona),
        title=title.strip(),
        issue=issue,
        branch=branch,
        decision=decision.strip(),
        design_doc=summary.design_doc,
        design=design_text(summary) + "\n",
        schema=_schema(ImplementationReport),
    )


def fix_prompt(
    persona: Persona, *, title: str, issue: int, branch: str, summary: DesignSummary, problems: str
) -> str:
    return _template("fix").substitute(
        _persona(persona),
        title=title.strip(),
        issue=issue,
        branch=branch,
        design_doc=summary.design_doc,
        problems=problems.strip(),
        schema=_schema(ImplementationReport),
    )


def review_prompt(
    persona: Persona,
    *,
    author: str,
    title: str,
    decision: str,
    issue: int,
    round_: int,
    summary: DesignSummary,
    tests: str,
    diff: str,
    previous_required: str = "",
) -> str:
    previous = ""
    if previous_required:
        previous = _section(
            "이전 라운드 [필수] 지적",
            previous_required + "\n\n각 항목이 해결됐는지 확인한다. 등급을 낮춰 넘기지 않는다",
        )
    return _template("review").substitute(
        _persona(persona),
        author=author,
        title=title.strip(),
        issue=issue,
        round=round_,
        decision=decision.strip(),
        design_doc=summary.design_doc,
        design=design_text(summary),
        tests=tests.strip(),
        previous=previous,
        diff=diff,
        schema=_schema(Review),
    )
