"""의견 렌더링 (운영 규약 2.2, 2.6).

게시용 요약은 1,500자 이내로 하고, 넘으면 요약만 게시하고 전문은 파일로 첨부한다.
"""

from dataclasses import dataclass

from bot.schemas import Opinion
from bot.workflow.chat import Attachment

MAX_POST_LENGTH = 1500
# 형식 오류 원문을 본문에 그대로 보일 최대 길이. 넘으면 첨부한다
_RAW_INLINE_LENGTH = 800


@dataclass(frozen=True)
class RenderedPost:
    text: str
    attachments: tuple[Attachment, ...] = ()


def render_opinion(opinion: Opinion, *, heading: str = "") -> str:
    """의견 전문. heading은 입장 앞에 붙는다 (예: "반박")."""
    title = f"**{opinion.stance.label}** — {opinion.conclusion}"
    if heading:
        title = f"{heading} · {title}"
    lines = [title, "", "근거"]
    lines += [f"- {reason}" for reason in opinion.reasons]
    lines += ["", "위험"]
    lines += [f"- {risk}" for risk in opinion.risks]
    lines += ["", "제안", opinion.proposal]
    return "\n".join(lines)


def render_opinion_post(opinion: Opinion, *, heading: str = "") -> RenderedPost:
    text = render_opinion(opinion, heading=heading)
    if len(text) <= MAX_POST_LENGTH:
        return RenderedPost(text)
    first_line = text.split("\n", 1)[0]
    summary = f"{first_line}\n\n전문이 길어 첨부 파일로 올린다."
    return RenderedPost(summary, (Attachment("opinion.md", text),))


def render_format_error(raw: str, error: str) -> RenderedPost:
    """재요청 후에도 형식에 맞지 않은 출력.

    원문을 '형식 오류' 표시와 함께 게시한다 (운영 규약 2.1).
    """
    reason = error.strip().splitlines()[0] if error.strip() else "형식 오류"
    head = f"**형식 오류** — 출력이 의견 형식에 맞지 않았다 ({reason})"
    body = raw.strip()
    if not body:
        return RenderedPost(f"{head}\n\n출력이 비어 있었다.")
    if len(body) <= _RAW_INLINE_LENGTH and "```" not in body:
        return RenderedPost(f"{head}\n\n원문:\n```\n{body}\n```")
    return RenderedPost(f"{head}\n\n원문은 첨부 파일로 올린다.", (Attachment("raw.txt", body),))
