# 저장소 작업 지침 (AGENTS.md)

이 저장소에서 작업하는 모든 코딩 에이전트(Claude Code, Codex 등)가 따르는 규칙이다.
v2 봇의 동작 규칙 전체는 [docs/운영-규약.md](docs/운영-규약.md)에 있다. 이 문서와 운영 규약이 다르면 운영 규약을 따른다.

## 공통 규칙

- 응답과 문서는 한국어로 작성한다
- 이모지를 쓰지 않는다
- Zero의 확인 없이 push하지 않는다

## 프로젝트 개요

ZeroSync는 Discord 기반 멀티 에이전트 오케스트레이터(v2)다. Zero의 아이디어를 Beta · Claude와 Alpha · Codex에게 전달하고, 결정·설계·구현·리뷰·merge·문서 반영 단계를 규칙대로 진행한다. 전환 배경은 [ADR-005](docs/아키텍처%20결정/ADR-005-Discord-오케스트레이터-전환.md)에 있다.

- 봇은 LLM이 아니라 결정론적 프로그램이다. 에이전트 출력의 JSON 블록을 검증해 옮길 뿐 해석하지 않는다
- 판단(방향, 설계 승인, merge, 문서 반영)은 Zero만 한다
- 외부(GitHub, Obsidian 볼트)에 쓰는 주체는 봇 하나다

## 구조

| 경로 | 내용 | 상태 |
|------|------|------|
| `bot/` | 봇 본체 (워크플로, 상태, 에이전트 호출, GitHub·볼트 쓰기). `python -m bot`이 진입점 | 골격 |
| `bot/schemas/` | 에이전트 출력 스키마(의견, 리뷰 판정, 설계 요약 일부)와 JSON 추출·검증 | 구현 |
| `bot/discord_io/` | Discord 입출력 계층. 워크플로 로직은 이 계층 밖에 둔다 | 골격 |
| `tests/` | pytest 테스트 | 골격 |
| `menubar/` | v1 Swift 메뉴바 앱 (`ZeroSync/`, `ZeroSync.xcodeproj`, 테스트 타깃) | 보류 |
| `docs/` | 봇 자체 개발 문서 | 사용 중 |

## 개발 환경과 명령

- Python 3.11 이상 (`.python-version`). 의존성과 도구 설정은 `pyproject.toml`에 있다
- 환경 준비: `python3.11 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
- 테스트: `pytest`
- 린트·포맷: `ruff check .`, `ruff format --check .`
- PR 전에 위 명령을 모두 통과시킨다

v1 메뉴바 앱을 수정할 때만 Xcode 명령을 쓴다. 저장소 루트에서 실행한다.

- 빌드: `xcodebuild -scheme ZeroSync -project menubar/ZeroSync.xcodeproj build`
- 테스트: `xcodebuild -scheme ZeroSync -project menubar/ZeroSync.xcodeproj test`

## 코딩 원칙

- 워크플로 로직은 Discord에 묶지 않는다. Discord 관련 코드는 `bot/discord_io/`에만 둔다
- 에이전트 출력은 pydantic 스키마로 검증한다. 저장, Discord 표시, Issue·PR·볼트 옮겨 적기는 모두 같은 JSON에서 만든다
- 스키마의 enum 값은 영문 키(`agree`, `required` 등)로 두고, 한국어 표시는 `label` 속성에서 만든다
- 멘션 여부, 브랜치 이름 검사, 볼트 쓰기 허용 경로처럼 규칙으로 정해진 동작은 단위 테스트로 고정한다

## 브랜치와 PR

- 기준 브랜치는 `develop`이다. 작업 브랜치는 develop에서 만들고, PR 대상도 develop이다
- `main`은 릴리스 기준이다. develop → main 반영은 Zero가 직접 한다
- 브랜치 이름: `<type>/<Issue번호>-<slug>` (예: `feat/12-vote-schema`). Issue가 없으면 번호 자리에 `0`을 쓴다. `claude/` 접두어는 쓰지 않는다
  - type: `feat`, `fix`, `refactor`, `docs`, `chore`
  - slug: 영문 소문자·숫자와 `-`, 40자 이내
- 스레드(작업 단위)마다 draft PR 하나를 연다. merge는 Zero가 GitHub에서 Merge commit 방식으로 한다
- develop·main에 직접 push하거나 merge하지 않는다. 작업 브랜치에서 push한 뒤에는 force push하지 않는다

## 커밋 메시지

- 형식: `<type>(<영역>): <요약>` + 빈 줄 + 본문(선택). 영역이 애매하면 생략한다 (`docs: ...`)
- type: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`
- `wip`, `수정` 같은 의미 없는 메시지는 쓰지 않는다

## 보안

- 봇 토큰, 웹훅 URL, API 키, `.env`는 커밋하지 않고 문서에도 적지 않는다
- 테스트·CLI 전체 로그(`.zerosync/`)는 커밋하지 않는다
- Xcode 사용자 상태 파일(`xcuserdata/`, `*.xcuserstate`)은 커밋하지 않는다

## 문서

- `docs/README.md`가 문서 인덱스다
- 중요한 기술 결정은 `docs/아키텍처 결정/`에 ADR로 남긴다 (다음 번호: ADR-006)
- 작업한 날에는 `docs/개발 일지/YYYY-MM-DD.md`에 한 것 / 막힌 것·발견한 것 / 다음 할 것을 기록한다
- 문제 해결 기록은 `docs/트러블슈팅/`에 남긴다
