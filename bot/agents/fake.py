"""테스트용 에이전트 러너 (SPEC 5.1).

미리 정해 둔 응답을 차례로 돌려주고, 받은 요청과 취소 요청을 기록한다.
"""

from collections.abc import Callable, Iterable
from pathlib import Path

from bot.agents.base import AgentName, AgentRequest, AgentResult, RunStatus

Response = str | AgentResult | Callable[[AgentRequest], str | AgentResult]


class FakeAgentRunner:
    def __init__(self, name: AgentName, responses: Iterable[Response] = ()):
        self.name: AgentName = name
        self._responses = list(responses)
        self.requests: list[AgentRequest] = []
        self.cancelled: list[str] = []

    def add_response(self, response: Response) -> None:
        self._responses.append(response)

    async def run(self, request: AgentRequest) -> AgentResult:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError(f"{self.name}: 준비된 응답이 없다 (요청 {request.run_id})")
        response = self._responses.pop(0)
        if callable(response):
            response = response(request)
        if isinstance(response, AgentResult):
            return response
        return AgentResult(
            status=RunStatus.OK,
            exit_code=0,
            stdout=response,
            stderr="",
            session_id=None,
            duration_sec=0.0,
            log_path=Path("fake") / f"{request.run_id}.log",
        )

    async def cancel(self, run_id: str) -> None:
        self.cancelled.append(run_id)
