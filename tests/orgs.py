"""테스트용 조직 설정.

LEGACY_ORG는 ADR-005 기준 흐름(Beta가 설계·구현, Alpha가 리뷰)을 엔진만 나눠 재현한다.
Beta는 claude 러너, Alpha는 codex 러너로 실행되어 기존 시나리오의 가짜 응답 순서를 그대로 쓴다.
"""

from bot.org import AgentSpec, Org, Roles, TeamSpec

LEGACY_ORG = Org(
    teams={
        "planning": TeamSpec(name="기획", lead="beta"),
        "dev": TeamSpec(name="개발", lead="alpha"),
    },
    agents={
        "beta": AgentSpec(
            display="Beta",
            team="planning",
            engine="claude",
            mbti="INFJ",
            perspective="사용 흐름과 범위",
            basic_question="이것을 써야 하는가",
        ),
        "alpha": AgentSpec(
            display="Alpha",
            team="dev",
            engine="codex",
            mbti="INTJ",
            perspective="구조와 위험",
            basic_question="왜 실패할 수 있나",
        ),
    },
    roles=Roles(
        opinions=("beta", "alpha"), design="beta", implement="beta", review="alpha", doc_sync="beta"
    ),
)
