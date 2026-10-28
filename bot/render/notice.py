"""[ZeroSync] 안내 문구."""

from bot.workflow.state import OPINION_NOTICE_AFTER, NoticeCode

_TEXT = {
    NoticeCode.AWAITING_DECISION: (
        f"질문이 {OPINION_NOTICE_AFTER}회를 넘었다. /decide 대기 중. "
        "방향이 정해지면 `/decide <방향>`으로 다음 단계로 넘어간다."
    ),
    NoticeCode.STOPPED: "작업을 중지했다. 실행 중인 에이전트를 종료했다.",
    NoticeCode.REJECTED: "지금 처리할 수 없는 입력이다.",
    NoticeCode.DECISION_RECORDED: (
        "결정을 기록하고 GitHub Issue를 만들었다. Beta가 설계를 시작한다. "
        "(볼트 결정 노트는 Phase 3에서 쓴다)"
    ),
    NoticeCode.AGENT_FAILED: "응답을 받지 못했다. 같은 질문을 다시 보내면 다시 요청한다.",
    NoticeCode.NOT_IMPLEMENTED: "아직 구현되지 않은 명령이다.",
    NoticeCode.NEEDS_HUMAN: "확인이 필요하다. 판단 후 /resume으로 재개하거나 /stop으로 끝낸다.",
    NoticeCode.INTERRUPTED: (
        "봇이 재시작되어 진행 중이던 단계를 멈췄다. 확인 후 판단하거나 /stop으로 끝낸다."
    ),
}


def render_notice(code: NoticeCode, detail: str = "") -> str:
    if code is NoticeCode.REJECTED and detail:
        return detail
    text = _TEXT[code]
    return f"{text}\n{detail}" if detail else text
