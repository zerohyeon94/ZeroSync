"""멘션 규칙 (운영 규약 2.5).

Zero가 행동해야 할 때만 멘션한다. 멘션 여부는 게시 시점의 종류로만 정하고,
나머지는 알림 없는(silent) 메시지로 보낸다.
"""

from enum import StrEnum


class Moment(StrEnum):
    """게시가 일어나는 시점."""

    # Zero가 행동해야 하는 시점
    OPINIONS_READY = "opinions_ready"  # 의견(또는 반박)이 모두 도착: /decide 또는 추가 질문
    DESIGN_READY = "design_ready"  # 설계 완료: /approve 또는 수정 요청
    FINAL_APPROVAL = "final_approval"  # APPROVED: PR 확인 후 merge
    DOC_SYNC_READY = "doc_sync_ready"  # 문서 반영안 도착: /approve, /revise, /skip
    NEEDS_HUMAN = "needs_human"  # 한도 초과, 형식 오류 반복: 판단 또는 /stop
    BOT_ERROR = "bot_error"  # 봇·CLI 오류, 타임아웃, 볼트 쓰기 실패 (#zerosync-ops)

    # 진행 알림
    IMPLEMENT_STARTED = "implement_started"
    TEST_RUNNING = "test_running"
    REVIEW_RUNNING = "review_running"
    TEST_RESULT = "test_result"
    REVIEW_ROUND_RESULT = "review_round_result"
    NOTICE = "notice"  # 명령 안내, 중지, 결정 기록 등


ACTION_REQUIRED = frozenset(
    {
        Moment.OPINIONS_READY,
        Moment.DESIGN_READY,
        Moment.FINAL_APPROVAL,
        Moment.DOC_SYNC_READY,
        Moment.NEEDS_HUMAN,
        Moment.BOT_ERROR,
    }
)


def should_mention(moment: Moment) -> bool:
    return moment in ACTION_REQUIRED
