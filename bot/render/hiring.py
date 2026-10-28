"""채용 제안 표시 (운영 규약 1.12, SPEC Q19)."""

from collections.abc import Mapping
from typing import Any

from bot.schemas import HiringProposal


def render_hiring_proposal(
    number: int, proposer: str, proposal: HiringProposal, evidence: Mapping[str, Any]
) -> str:
    """Zero에게 올리는 채용 제안. 숫자 근거는 봇이 DB에서 계산한 값이다."""
    runs = evidence.get("runs", {})
    run_text = ", ".join(f"{status} {count}" for status, count in sorted(runs.items())) or "없음"
    lines = [
        f"**채용 제안 #{number}** — {proposer}",
        f"- 종류: {proposal.kind.label} / 팀: {proposal.team} / 역할: {proposal.role}",
        f"- 근거: {proposal.reason}",
        "- 관련 작업:",
        *(f"  - {case}" for case in proposal.cases),
        f"- 맡길 업무: {proposal.duties}",
        f"- 원하는 성격: {proposal.mbti or '정하지 않음'}",
        "- 역량:",
        *(f"  - {item}" for item in proposal.competencies),
        f"- 채용하지 않으면: {proposal.if_not_hired}",
        f"- 봇 기록: {proposer}의 실행 결과 {run_text} / "
        f"전체 오류 기록 {evidence.get('errors', 0)}건",
        "",
        f"`/hire 결정:수락 번호:{number}` 또는 "
        f"`/hire 결정:거절 번호:{number} 메모:<이유>`로 답한다. "
        "수락하면 Zero가 org.yaml과 인격 파일을 추가한다.",
    ]
    return "\n".join(lines)


def rejected_line(payload: Mapping[str, Any], note: str | None) -> str:
    """프롬프트에 넣는 거절된 제안 한 줄 (같은 제안 반복 방지)."""
    proposal = HiringProposal.model_validate(payload)
    return f"{proposal.kind.label} {proposal.team} {proposal.role}: {note or '이유 없음'}"
