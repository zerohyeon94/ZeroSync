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
        "결정을 기록했다. Issue 생성, 볼트 기록, 설계 단계는 아직 구현되지 않아 여기서 멈춘다."
    ),
    NoticeCode.AGENT_FAILED: "응답을 받지 못했다. 같은 질문을 다시 보내면 다시 요청한다.",
    NoticeCode.NOT_IMPLEMENTED: "아직 구현되지 않은 명령이다.",
}


def render_notice(code: NoticeCode, detail: str = "") -> str:
    if code is NoticeCode.REJECTED and detail:
        return detail
    text = _TEXT[code]
    return f"{text}\n{detail}" if detail else text
