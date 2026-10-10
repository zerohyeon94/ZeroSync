# ZeroSync v2 봇 설계서 (SPEC)

> 작성: 2026-09-30 (claude.ai 초안) | 갱신: 2026-10-07 (11장 미결 사항 결정) | 상태: Phase 1 진행 중
> 상위 문서: [운영 규약](운영-규약.md). **이 문서와 운영 규약이 다르면 운영 규약을 따른다.**
> 관련: [ADR-005](아키텍처%20결정/ADR-005-Discord-오케스트레이터-전환.md), [AGENTS.md](../AGENTS.md)

---

## 0. 이 문서의 역할과 표기

운영 규약은 **무엇을 지켜야 하는가**(역할, 권한, 대화 형태, 기록 위치, GitHub 규칙)를 정한다.
이 문서는 **봇을 어떻게 만드는가**(상태 머신, 명령어, 모듈, 데이터 모델, 에이전트 호출 규약, 운영 방식)를 정한다.
운영 규약에 이미 있는 내용은 절 번호로 참조만 하고 반복하지 않는다.

| 표기 | 뜻 |
|---|---|
| [확정] | 운영 규약 또는 Zero의 결정으로 정해짐 |
| [제안] | 이 문서가 제안하는 값. Zero의 확인 전까지 구현 기본값으로만 쓴다 |
| [미결] | 결정이 필요함. 11장에 모아 둠 |
| [검증 필요] | 맥에서 실제로 확인해야 하는 가정. 10장에 모아 둠 |

이 문서를 바탕으로 구현할 때, [제안]과 [미결] 항목을 임의로 확정하지 않는다. 구현에 필요한 순간 Zero에게 묻는다.

---

## 1. 목표와 범위

### 1.1 완료 기준 (프로젝트 목표)
가게씨 Discord 포럼에서 "아이디어 → Beta·Alpha 의견 → Zero 결정 → Beta 설계·구현 → Alpha 리뷰(최대 3회) → Zero merge → 문서 반영" 한 사이클을 실제로 완주하고, 봇이 맥에서 상시 운영된다.

### 1.2 범위 밖
- 봇이 내용을 판단하거나 방향을 정하는 기능 (봇은 LLM이 아니다. 운영 규약 1.1-3)
- v1의 일정·번아웃 관리 기능 (운영 규약 1.2)
- main 브랜치 관련 작업, 릴리스 (운영 규약 4.1)
- 여러 사용자 지원. 명령 권한자는 Zero 한 명이다

---

## 2. 실행 구조

### 2.1 프로세스 구성 [확정]

```
launchd (LaunchAgent, 로그인 사용자 세션)
  └─ caffeinate -is
       └─ python -m bot          ← 상시 실행되는 유일한 프로세스 (asyncio 이벤트 루프 하나)
            ├─ Discord Gateway WebSocket (맥에서 밖으로 나가는 연결. 포트 개방 불필요)
            ├─ 백그라운드 태스크: PR merge 폴링, 방치 작업 재멘션
            ├─ SQLite (상태, 이벤트, 에이전트 출력 원본)
            └─ 필요할 때만 띄우는 자식 프로세스
                 ├─ claude -p ...      (헤드리스, 끝나면 종료)
                 ├─ codex exec ...     (헤드리스, 끝나면 종료)
                 ├─ <projects.yaml의 test 명령>  (전역 락 아래 하나씩)
                 └─ git, gh
```

- 봇은 자식 프로세스를 `asyncio.create_subprocess_exec`로 띄운다. 셸 문자열(`shell=True`)은 쓰지 않는다 (프롬프트에 섞인 문자가 셸 명령으로 해석되는 것을 막기 위해)
- 자식 프로세스가 실행되는 동안에도 이벤트 루프는 `/stop`, `/status`, `/ping`에 응답해야 한다
- 같은 맥에서 봇 인스턴스는 하나만 실행한다. 시작 시 lock 파일(`paths.db`와 같은 폴더의 `bot.lock`, 기본 `~/.zerosync/bot.lock`)을 `flock`으로 잡지 못하면 종료한다. 프로세스가 끝나면 운영체제가 락을 푼다 (2026-10-07 구현)

### 2.2 사람이 쓰는 화면
봇 자체에는 UI가 없다. Zero는 Discord(지시·알림), GitHub(PR 확인·merge), Obsidian(결정·기능 문서)을 쓴다. Phase 6의 메뉴바 대시보드는 SQLite만 읽는다 (운영 규약 1.11).

---

## 3. 상태 머신

### 3.1 상태 [제안]

운영 규약 1.5의 단계를 "봇이 일하는 중"과 "Zero를 기다리는 중"으로 나눠 상태로 만든다. Zero 대기 상태는 운영 규약 2.5의 멘션·재멘션 대상이다.

| 상태 | 실행 주체 | 종류 | 설명 |
|---|---|---|---|
| `OPINIONS` | Beta, Alpha | Zero 대기 | 의견·추가 질문·반박. `/decide` 전까지 유지 (운영 규약 1.6) |
| `DESIGNING` | Beta | 실행 중 | worktree 생성, 설계 문서 작성, 설계 요약 JSON 출력 |
| `AWAIT_DESIGN_APPROVAL` | - | Zero 대기 | `/approve` 또는 `/revise` |
| `IMPLEMENTING` | Beta | 실행 중 | 작업 브랜치 로컬 커밋 |
| `TESTING` | 봇 | 실행 중 | test 명령 실행 (전역 락) |
| `REVIEWING` | Alpha | 실행 중 | diff + 설계 요약 + 테스트 결과 → 판정 |
| `FIXING` | Beta | 실행 중 | [필수] 지적 또는 테스트 실패 대응 |
| `AWAIT_MERGE` | - | Zero 대기 | APPROVED, draft 해제됨. GitHub에서 merge |
| `DOC_DRAFTING` | Beta | 실행 중 | DOC_SYNC 수정안 작성 (읽기 전용) |
| `AWAIT_DOC_APPROVAL` | - | Zero 대기 | `/approve`, `/revise`, `/skip` |
| `DONE` | - | 종료 | |
| `STOPPED` | - | 종료 | `/stop` |
| `NEEDS_HUMAN` | - | Zero 대기 | 자동 진행 한도 초과 |

작업(task)은 Zero가 포럼에 게시글을 올리는 순간 `OPINIONS`로 생성된다 (초안의 `IDEA` 상태와 `/idea` 명령은 두지 않는다 [제안]).

### 3.2 전이

```
(포럼 게시글) ─▶ OPINIONS ──/decide──▶ DESIGNING ──▶ AWAIT_DESIGN_APPROVAL
                                           ▲              │ /approve
                                           └──/revise─────┤
                                                          ▼
                                IMPLEMENTING ──▶ TESTING ──(통과)──▶ REVIEWING
                                     ▲              │(실패)            │
                                     │              ▼                  │ CHANGES_REQUESTED
                                     └────────── FIXING ◀──────────────┘
                                                                       │ APPROVED
                                                                       ▼
            DONE ◀── AWAIT_DOC_APPROVAL ◀── DOC_DRAFTING ◀──(merge 감지)── AWAIT_MERGE
                      │ /revise ─▶ DOC_DRAFTING
                      │ /skip   ─▶ DONE (결정 노트만 완료 처리, worktree 정리)

어느 상태에서든 /stop ─▶ STOPPED
한도 초과 ─▶ NEEDS_HUMAN
```

| 현재 | 이벤트 | 다음 | 부수 효과 |
|---|---|---|---|
| OPINIONS | 일반 메시지, `@claude`, `@codex`, `/debate` | OPINIONS | 해당 에이전트 호출, 의견 게시 |
| OPINIONS | `/decide <방향>` | DESIGNING | Issue 생성(1.8), 볼트 결정 노트·논의 목록(3.5) |
| DESIGNING | 설계 JSON 검증 통과 | AWAIT_DESIGN_APPROVAL | 브랜치 생성·push(4.3), Issue 코멘트, 멘션 |
| AWAIT_DESIGN_APPROVAL | `/approve` | IMPLEMENTING | 라벨 `type:*`, 볼트 갱신(3.5) |
| AWAIT_DESIGN_APPROVAL | `/revise <요청>` | DESIGNING | 같은 설계 파일 수정 커밋 |
| IMPLEMENTING, FIXING | 커밋 완료 | TESTING | 커밋 메시지 형식 검사(4.4) 후 push |
| TESTING | 통과 | REVIEWING | 첫 회에 draft PR 생성, 이후 PR 본문 갱신 |
| TESTING | 실패 | FIXING | `test_retry += 1`. Codex 호출 생략 (1.7) |
| REVIEWING | CHANGES_REQUESTED | FIXING | `review_round += 1`, PR 코멘트 |
| REVIEWING | APPROVED | AWAIT_MERGE | draft 해제, 남은 [권장] 개수 표시, 멘션 |
| AWAIT_MERGE | `/fix 권장 반영` | FIXING | [권장] 항목을 대상으로 1회 수정 (2.3) |
| AWAIT_MERGE | PR merge 감지 | DOC_DRAFTING | Issue 코멘트 후 종료 (4.6) |
| AWAIT_DOC_APPROVAL | `/approve` | DONE | 볼트 쓰기·커밋, worktree 정리 |
| AWAIT_DOC_APPROVAL | `/skip` | DONE | 결정 노트만 완료 처리, worktree 정리 (운영 규약 3.9-6, 4.6) |
| 모든 상태 | `/stop` | STOPPED | 실행 중 CLI 종료, Issue·브랜치·볼트 처리 (1.8, 3.3, 3.5) |
| 실행 중 상태 | 한도 초과 | NEEDS_HUMAN | `needs-human` 라벨, 멘션 |
| NEEDS_HUMAN | `/resume` | 직전 상태 | 카운터는 유지하고 초과한 한도만 1회 늘린다 [확정] (Q4) |

### 3.3 한도 [확정 + 제안]

| 항목 | 값 | 근거 |
|---|---|---|
| 리뷰 라운드 | 3회 초과 시 NEEDS_HUMAN | 운영 규약 1.7, 2.5 |
| 테스트 실패 재시도 | 2회 초과 시 NEEDS_HUMAN | 운영 규약 1.7, Q2 [확정] |
| 형식 오류 | 재요청 1회 후에도 실패하면 원문 게시 + NEEDS_HUMAN. OPINIONS(의견·반박)는 원문을 "형식 오류" 표시와 함께 게시하고 멘션한 뒤 OPINIONS를 유지한다 [확정] (2026-10-10 Zero 결정) | 운영 규약 2.1, 2.5 |
| CLI 타임아웃 | 3,600초 | `projects.yaml`의 `cli_timeout_sec` |
| OPINIONS 질문 수 | 제한 없음. 5회 초과 시 "/decide 대기 중" 한 줄 알림 (넘는 순간 1회). 처음 게시글과 `/debate`는 세지 않고, 게시글 뒤 Zero의 일반 메시지와 `@claude`/`@codex` 메시지만 1회씩 센다 [확정] (2026-10-07) | 운영 규약 1.6 |
| 재멘션 | Zero 대기 24시간 초과 시 1회 | 운영 규약 2.5 |

### 3.4 구현 원칙
- 전이 규칙은 `bot/workflow/state.py`에 **순수 함수**로 둔다: `(현재 상태, 이벤트) → (다음 상태, 실행할 효과 목록)`. I/O 없이 단위 테스트로 전부 고정한다
- 효과(에이전트 호출, GitHub, 볼트, 게시)는 `workflow/engine.py`가 인터페이스를 통해 실행한다
- 상태 변경은 SQLite 트랜잭션 안에서 이벤트 기록과 함께 저장한다. 봇이 재시작되면 "실행 중" 상태의 작업은 NEEDS_HUMAN으로 돌리고 Zero에게 알린다 (중간 결과를 신뢰하지 않음) [확정] (Q8)

---

## 4. Discord 명령어

권한 검사: 모든 명령과 메시지는 Zero의 Discord 사용자 ID일 때만 처리한다. 그 밖의 입력은 무시하고 로그만 남긴다 (운영 규약 1.3).

| 명령 | 가능한 상태 | 동작 | 상태 |
|---|---|---|---|
| (게시글 작성) | - | 작업 생성 → OPINIONS, 두 에이전트 의견 병렬 요청 | [확정] |
| (게시글에 일반 메시지) | OPINIONS | 둘 다 응답. 메시지가 `@claude`/`@codex`로 시작하면 지정된 쪽만 | [확정] |
| `/debate` | OPINIONS | 상대 의견에 대한 반박 1회씩 | [확정] |
| `/decide <방향>` | OPINIONS | 방향 확정 → DESIGNING | [확정] |
| `/approve` | AWAIT_DESIGN_APPROVAL, AWAIT_DOC_APPROVAL | 현재 단계 승인 | [확정] |
| `/revise <요청>` | AWAIT_DESIGN_APPROVAL, AWAIT_DOC_APPROVAL | 수정안 다시 작성 | [확정] (설계 단계는 Q7) |
| `/skip` | AWAIT_DOC_APPROVAL | 기능 정의서 반영 생략 | [확정] |
| `/fix 권장 반영` | AWAIT_MERGE | [권장] 항목 1회 추가 수정 | [확정] |
| `/stop` | 종료 상태 외 전부 | 긴급 정지 | [확정] |
| `/resume` | NEEDS_HUMAN | 직전 상태에서 재개 | [확정] (Q4) |
| `/status` | 전부 | 상태, 라운드 수, 재시도 수, 대기 시간 | [확정] |
| `/ping` | 전부 (#zerosync-ops에서도) | 봇 생존, 실행 중 CLI 수 | [확정] |

- 명령은 discord.py의 앱 명령(슬래시 명령)으로 등록하고, 해당 게시글(스레드) 안에서만 동작한다. 다른 곳에서 쓰면 짧은 오류만 보낸다
- 상태와 맞지 않는 명령은 상태를 바꾸지 않고 현재 상태와 가능한 명령을 알려 준다

---

## 5. 에이전트 호출 규약

### 5.1 AgentRunner 인터페이스 [확정 원칙, 시그니처는 제안]

```python
class AgentRunner(Protocol):
    name: Literal["claude", "codex"]

    async def run(self, request: AgentRequest) -> AgentResult: ...
    async def cancel(self, run_id: str) -> None: ...

@dataclass(frozen=True)
class AgentRequest:
    run_id: str
    task_id: int
    stage: Stage                 # OPINION, DEBATE, DESIGN, IMPLEMENT, FIX, REVIEW, DOC_SYNC
    prompt: str
    cwd: Path                    # 앱 저장소 또는 작업 worktree
    mode: Literal["read_only", "write_worktree"]
    timeout_sec: int
    resume_session: str | None = None   # Claude 세션 이어가기 (최적화, 필수 아님)
    output_schema: Mapping[str, Any] | None = None  # 응답 JSON 스키마. 주면 CLI 구조화 출력으로 강제

@dataclass(frozen=True)
class AgentResult:
    status: RunStatus            # ok | error | timeout | cancelled
    exit_code: int | None        # 프로세스를 띄우지 못하면 None
    stdout: str                  # parse_agent_output()에 넘기는 원문
    stderr: str
    session_id: str | None
    duration_sec: float
    log_path: Path               # ~/.zerosync/runs/<run_id>.log
```

- 실제 구현: `ClaudeCliRunner`, `CodexCliRunner`. 테스트: `FakeAgentRunner`(정해 둔 응답을 돌려줌)
- `status`는 종료 코드만으로 구분할 수 없는 타임아웃·취소를 나타낸다. 8장 `agent_runs.status`의 `running`·`invalid_output`은 저장 계층과 출력 검증이 정한다 (2026-10-07 Zero 승인으로 추가)
- 구현됨: `bot/agents/base.py`(인터페이스), `bot/agents/process.py`(자식 프로세스 실행, 타임아웃·취소, 실행 로그), `bot/agents/fake.py`, `bot/agents/claude.py`, `bot/agents/codex.py`
- `output_schema`는 2026-10-10 추가 (Zero 결정: 스키마 강제 우선). 강제 출력도 `parse_agent_output`으로 다시 검증한다
- 러너는 출력을 해석하지 않는다. JSON 추출과 검증은 `bot/schemas/extract.py`의 `parse_agent_output`가 한다 (구현됨)

### 5.2 단계별 명령 [확정, 2026-10-10 시험 호출로 확인]

| 단계 | 에이전트 | 명령 골격 | 권한 |
|---|---|---|---|
| OPINION, DEBATE | Claude | `claude -p --permission-mode plan` | 읽기 전용 |
| OPINION, DEBATE, REVIEW | Codex | `codex exec --cd <cwd> --sandbox read-only --ephemeral --ignore-user-config -o <runs>/<run_id>.last.txt -` | 읽기 전용 |
| DESIGN | Claude | `claude -p --permission-mode dontAsk --allowedTools Read Glob Grep "Edit(docs/설계/**)" "Write(docs/설계/**)" <로컬 git>` | worktree의 docs만 |
| IMPLEMENT, FIX | Claude | `claude -p --permission-mode acceptEdits --allowedTools Read Glob Grep Edit Write <로컬 git>` (+ `--resume <세션ID>`) | 작업 worktree |
| DOC_SYNC | Claude | `claude -p --permission-mode plan` | 읽기 전용 (수정안은 JSON으로만) |

- Claude 공통: `--output-format json --permission-prompts none --strict-mcp-config --disallowedTools "Bash(git push:*)" "Bash(git pull:*)" "Bash(git fetch:*)" "Bash(git remote:*)" "Read(**/.env)" "Edit(**/.env)" "Write(**/.env)"`. `<로컬 git>`은 `Bash(git status|diff|log|show|add|commit:*)`
  - `--permission-prompts none`: 허용 목록에 없어 승인이 필요한 동작은 자동 거부되고 결과 JSON의 `permission_denials`에 남는다. `ls` 같은 읽기 전용 명령은 목록에 없어도 실행된다
  - `--strict-mcp-config`: 사용자 MCP 서버(Notion, Slack 등)를 불러오지 않는다. `--bare`는 OAuth 로그인을 읽지 않아 구독 로그인과 함께 쓸 수 없다
- 프롬프트는 두 CLI 모두 stdin으로 넘긴다. 실행 로그의 argv에 프롬프트가 남지 않는다
- 단계별 모델은 `projects.yaml`의 `cli.claude_models`·`cli.codex_models`로 정한다 (9.1, 2026-10-10 Zero 결정)
- Codex는 쓰기 단계를 맡지 않으므로 러너가 쓰기 모드 요청을 거부한다

- 구조화 출력: `AgentRequest.output_schema`가 있으면 Claude는 `--json-schema`, Codex는 `--output-schema <파일>`로 강제한다. 없으면 프롬프트로 ```json 블록을 요청한다 (운영 규약 2.1). pydantic `model_json_schema()` 결과를 두 CLI 모두 그대로 받는다 (확인됨)
  - Claude 결과 JSON: `structured_output`(스키마 강제 시)을 우선하고, 없으면 `result` 문자열을 응답 본문으로 쓴다. `is_error: true`면 종료 코드가 0이어도 실패로 본다. 세션 ID는 `session_id`
  - Codex: `-o` 파일의 마지막 메시지를 응답 본문으로 쓴다. 진행 기록은 stderr로 나와 실행 로그에만 남는다. 세션 ID는 쓰지 않는다(`--ephemeral`)
- Claude의 쓰기 단계 권한은 허용 도구 목록으로 좁힌다. `git push`, 원격 관련 git 명령, `.env` 접근은 금지 목록에 넣는다 (운영 규약 1.3). 시험 호출에서 push, `.env` 읽기, 작업 폴더 밖 쓰기, 설계 단계의 `docs/설계/` 밖 쓰기가 모두 거부됨을 확인했다
- 맥락은 매번 SQLite 기록으로 재구성해 프롬프트에 넣는다. 세션 이어가기는 실패해도 동작에 영향이 없어야 한다 (운영 규약 1.6)
- PATH는 launchd 환경에서도 `claude`, `codex`를 찾도록 `projects.yaml`의 `cli.claude`·`cli.codex`에 절대 경로로 지정할 수 있다 (Homebrew 설치 시 `/opt/homebrew/bin/claude`, `/opt/homebrew/bin/codex`)

### 5.3 프롬프트 [제안]
- 위치: `bot/prompts/<stage>.md` (템플릿 문자열, `string.Template`의 `$이름`). 코드에 긴 문자열을 넣지 않는다
- 구현됨: `opinion.md`, `debate.md` (2026-10-10). 스냅샷은 `tests/snapshots/`
- 공통 구성: 인격과 관점(운영 규약 1.2, 1.4) → 작업 맥락(제목, 원문, 결정 원문, 이전 출력) → 단계별 지시 → 출력 스키마(`Model.model_json_schema()`로 생성) → 금지 사항
- 첫 의견은 상대 의견을 넣지 않는다. 두 번째 질문부터 게시글 전체 흐름을 넣는다 (운영 규약 1.6)
- 프롬프트 렌더링은 순수 함수로 두고 스냅샷 테스트로 고정한다

### 5.4 출력 스키마

| 단계 | 스키마 | 상태 |
|---|---|---|
| OPINION | `Opinion` (stance, conclusion, reasons, risks, proposal) | 구현됨 |
| DEBATE | `Opinion` 재사용. stance는 상대 의견에 대한 입장 | [제안] |
| REVIEW | `Review` (verdict, summary, findings) | 구현됨 |
| DESIGN | `DesignSummary` (change_type, target_feature, slug + 아래 추가 필드) | 일부 구현 |
| IMPLEMENT, FIX | `ImplementationReport` | [제안] |
| DOC_SYNC | `DocSyncProposal` | [제안] (형태는 운영 규약 3.9-3) |

`DesignSummary` 추가 필드 [확정] (Q1, 대상 기능은 1개)

| 키 | 타입·제약 | 쓰임 |
|---|---|---|
| `title` | 한 줄, 80자 | PR 제목 `<type>(<영역>): <요약>`의 요약 |
| `scope` | 영문 소문자 영역 이름 또는 null | 커밋·PR 제목의 영역 (4.4) |
| `summary` | 500자 | Discord·Issue 코멘트·결정 노트의 설계 요약 |
| `changes` | 1~8개, 항목 200자 | 바꿀 파일·구성 요소 |
| `test_plan` | 1~6개, 항목 200자 | 추가·수정할 테스트 |
| `risks` | 0~3개, 항목 200자 | 설계상 위험 |
| `design_doc` | `docs/설계/<Issue번호>-<slug>.md` 형식 | 봇이 파일 존재를 확인 |

`target_feature` 검증 규칙 (구현됨, PR #10): 봇이 넘긴 `기능/` 파일 이름 목록을 기준으로, `feature_add`는 목록에 없는 이름, 나머지 변경 유형은 목록에 있는 이름이어야 한다 (운영 규약 3.8, 3.9-4).

`ImplementationReport` [제안]: `changes_summary`(500자), `design_intent`(300자), `check_points`(0~5개), FIX 단계에서는 `responses`(지적 번호별 `fixed` / `declined` + 사유). PR 본문의 Claude 담당 항목(운영 규약 1.9)이 여기서 나온다.

`DocSyncProposal` [제안]: `summary`(300자), `files`(1~5개: `path`, `action`(`create`/`update`), `content` 전체).

---

## 6. 외부 연동

### 6.1 Discord (`bot/discord_io/`)
- 워크플로는 `ChatIO` 인터페이스만 안다: `post(thread, author, text, *, mention, attachments) -> 메시지 ID`, `notify_ops(text, *, mention)`. 인터페이스는 `bot/workflow/chat.py`에 두고 `bot/discord_io/`가 구현한다 (의존 방향, 7장). `set_tags`는 태그 이름이 정해지면 추가한다 [제안]
- `mention=False`면 알림 없는 메시지로 보낸다. 멘션 문자열(`<@Zero ID>`)과 1,900자 분할은 구현 쪽 책임이다
- 의견·반박은 두 에이전트 응답이 모두 끝난 뒤 Beta, Alpha 순서로 게시하고, 마지막 게시에서 멘션한다. 실행 실패한 쪽은 그 자리에 [ZeroSync] 안내를 게시하고 #zerosync-ops에 알린다 (2026-10-10 구현)
- 게시 이름: `[Beta · Claude]`, `[Alpha · Codex]`, `[ZeroSync]`(운영 규약 1.2). 에이전트 메시지는 웹훅의 username 지정으로 게시한다
- 웹훅은 봇이 시작할 때 각 포럼 채널에서 찾거나 만든다(Manage Webhooks 권한). 웹훅 URL을 `.env`에 두지 않는다 [확정] (Q6)
- 멘션은 이벤트 종류의 `ACTION_REQUIRED` 집합으로만 결정한다. 나머지는 silent 메시지 (운영 규약 2.5) [검증 필요: 웹훅 silent]
- 길이: 게시용 요약 1,500자 이내, 넘는 전문은 파일 첨부. 1,900자 분할은 안전장치 (운영 규약 2.6)
- render 계층(`bot/render/`)이 스키마 객체를 텍스트로 바꾼다. Discord에 의존하지 않으므로 Issue·PR·볼트 문서도 같은 계층에서 만든다
- 포럼 태그: `의견중` `결정됨` `설계` `구현` `리뷰` `merge대기` `문서반영` `완료` `중지` `확인필요` [제안]

### 6.2 GitHub (`bot/github/`)
- `gh` CLI를 감싼 `GitHubClient` 인터페이스: Issue 생성·코멘트·종료·라벨, draft PR 생성·본문 갱신·코멘트·draft 해제, PR 상태 조회 [제안]
- 봇의 git 작업은 `GitOps` 인터페이스: worktree 생성·삭제, 브랜치 생성, 커밋 메시지 검사, push. push 전 두 조건 검사(운영 규약 4.7)는 단위 테스트로 고정
- merge 감지: `AWAIT_MERGE` 상태의 PR을 5분 간격으로 조회 (운영 규약 3.9-1)
- 첫 실행 시 라벨이 없으면 만든다 (운영 규약 4.8)

### 6.3 Obsidian 볼트 (`bot/vault/`)
- 쓰기 허용 경로를 코드에서 강제한다: `결정/` 전체, 그리고 DOC_SYNC 승인 시의 `기능/*.md`와 허브 파일 (운영 규약 3.4)
- 논의 목록은 SQLite 기록으로 매번 통째로 다시 만든다 (3.6). 결정 노트는 `source_id`로 찾아 갱신한다 (3.7)
- DOC_SYNC 승인 직전에 대상 파일 해시를 비교한다 (3.9-7)
- 볼트 git 커밋은 자기 파일만 경로를 지정해 커밋한다 (3.10)

### 6.4 테스트 실행 (`bot/testrun.py`)
- `projects.yaml`의 `test` 명령을 전역 락 아래에서 실행한다 (운영 규약 1.7)
- 결과 요약: 종료 코드, 통과·실패 수, 실패 테스트명, 소요 시간. 전체 로그는 `~/.zerosync/runs/`
- xcodebuild 결과 파싱(통과·실패 수)은 `-resultBundlePath`의 결과 번들 또는 출력 텍스트에서 한다 [검증 필요]

---

## 7. 모듈 구조

현재 develop에 있는 것은 `bot/__main__.py`(골격), `bot/schemas/`(구현), `bot/agents/`(인터페이스·프로세스 실행·가짜 러너·Claude·Codex CLI 러너), `bot/clock.py`, `bot/store/`(SQLite 스키마 v1·저장소), `bot/workflow/`(상태 enum과 OPINIONS 범위 전이, ChatIO 인터페이스, 멘션 규칙, OPINIONS 단계 엔진), `bot/prompts/`(의견·반박), `bot/render/`(의견·안내), `bot/config.py`(설정 로더), `bot/locks.py`(단일 인스턴스 락), `bot/discord_io/`(빈 패키지)다. `bot/__main__.py`는 설정 로드와 락까지만 한다. 아래는 목표 구조다 [제안].

```
bot/
  __main__.py          # 진입점: 설정 로드, 단일 인스턴스 락, 이벤트 루프 시작
  config.py            # projects.yaml + .env 로더 (pydantic 모델)
  schemas/             # 에이전트 출력 스키마 (구현됨: opinion, review, design 일부, extract)
  prompts/             # 단계별 프롬프트 템플릿 (.md)
  agents/
    base.py            # AgentRunner, AgentRequest, AgentResult
    process.py         # 자식 프로세스 실행 (셸 미사용, 타임아웃·취소, 실행 로그)
    claude.py          # ClaudeCliRunner
    codex.py           # CodexCliRunner
    fake.py            # 테스트용 FakeAgentRunner
  workflow/
    state.py           # 상태 enum, 이벤트, 전이 규칙 (순수 함수)
    engine.py          # 효과 실행, 한도 관리
    chat.py            # ChatIO 인터페이스, 테스트용 FakeChatIO
    mentions.py        # ACTION_REQUIRED 집합, 재멘션 판정
  store/
    db.py              # SQLite 연결, 마이그레이션
    repo.py            # tasks, events, agent_runs 접근
  render/              # 스키마 → Discord·Issue·PR·볼트 텍스트
  discord_io/          # ChatIO 구현, 슬래시 명령, 웹훅
  github/              # GitHubClient(gh), GitOps(git)
  vault/               # 결정 노트, 논의 목록, DOC_SYNC 쓰기
  testrun.py           # 테스트 명령 실행과 결과 요약
  locks.py             # 전역 빌드 락, 작업별 실행 락
  clock.py             # 현재 시각 (테스트에서 고정)
tests/
deploy/
  com.zerosync.orchestrator.plist
```

의존 방향: `discord_io`, `github`, `vault`, `agents` → (인터페이스) ← `workflow`. `workflow`는 discord.py를 import하지 않는다 (운영 규약 1.1-5).

---

## 8. 데이터 모델 (SQLite) [제안]

파일: `~/.zerosync/zerosync.db`. 시각은 UTC ISO 8601 문자열.

```sql
CREATE TABLE tasks (
  id               INTEGER PRIMARY KEY,
  project          TEXT NOT NULL,                 -- projects.yaml 키
  discord_thread   TEXT NOT NULL UNIQUE,
  title            TEXT NOT NULL,
  state            TEXT NOT NULL,                 -- 3.1의 상태
  prev_state       TEXT,                          -- NEEDS_HUMAN에서 돌아갈 상태
  review_round     INTEGER NOT NULL DEFAULT 0,
  test_retry       INTEGER NOT NULL DEFAULT 0,
  opinion_rounds   INTEGER NOT NULL DEFAULT 0,
  issue_number     INTEGER,
  pr_number        INTEGER,
  branch           TEXT,                          -- 봇이 만든 브랜치 (push 보호 4.7-2)
  worktree         TEXT,
  claude_session   TEXT,
  waiting_since    TEXT,                          -- Zero 대기 시작 시각
  reminded_at      TEXT,                          -- 재멘션 1회 기록
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL
);

CREATE TABLE events (
  id               INTEGER PRIMARY KEY,
  task_id          INTEGER NOT NULL REFERENCES tasks(id),
  actor            TEXT NOT NULL,   -- zero | claude | codex | bot
  kind             TEXT NOT NULL,   -- message | opinion | debate | decision | design | impl
                                    -- | test | review | fix | doc_sync | command | error
  payload          TEXT NOT NULL,   -- JSON: 검증된 스키마 원본 또는 원문
  discord_message  TEXT,
  created_at       TEXT NOT NULL
);

CREATE TABLE agent_runs (
  id               TEXT PRIMARY KEY,               -- run_id
  task_id          INTEGER NOT NULL REFERENCES tasks(id),
  agent            TEXT NOT NULL,                  -- claude | codex
  stage            TEXT NOT NULL,
  exit_code        INTEGER,
  status           TEXT NOT NULL,                  -- running | ok | invalid_output | timeout
                                                   -- | cancelled | error
  log_path         TEXT,
  started_at       TEXT NOT NULL,
  finished_at      TEXT
);
```

- 비동기 접근은 `aiosqlite`를 쓴다. 스키마 변경은 `PRAGMA user_version`으로 버전을 관리한다
- 에이전트 출력 원본(검증된 JSON)은 `events.payload`에 둔다. 운영 규약 3.2의 "에이전트 출력 원본 JSON은 SQLite"에 해당

---

## 9. 설정과 운영

### 9.1 `bot/projects.yaml` [제안]

저장소에는 값을 비운 `bot/projects.example.yaml`만 커밋하고, 실제 값이 든 `bot/projects.yaml`은 `.gitignore`에 넣는다 [확정] (Q11, 공개 저장소)

```yaml
projects:
  gagessi:
    forum_channel_id: "..."
    repo: ~/Dev/Gagessi
    github: zerohyeon94/Gagessi
    base_branch: develop
    test: xcodebuild test -scheme Gagessi -destination 'platform=iOS Simulator,name=iPhone 16'
    vault_dir: 일일 예산 관리 앱
    vault_hub: 가게씨.md
    vault_tag: brain/gagaessi
    vault_slug: gagaessi
  # orot, jday도 같은 형식 (운영 규약 3.4 표)

paths:
  vault_projects: ~/Library/Mobile Documents/iCloud~md~obsidian/Documents/zerohyeon-labs/Projects
  worktrees: ~/.zerosync/worktrees
  runs: ~/.zerosync/runs
  db: ~/.zerosync/zerosync.db

cli:
  claude: claude        # launchd PATH 문제 시 절대 경로
  codex: codex
  claude_models:        # 단계별 모델. 적지 않은 단계는 CLI 기본값 (2026-10-10 Zero 결정)
    opinion: sonnet
    design: opus
  codex_models:         # opinion, debate, review만
    review: <모델>

limits:
  max_review_rounds: 3
  max_test_retries: 2   # Q2 확정
  cli_timeout_sec: 3600
  concurrent_builds: 1
  merge_poll_sec: 300
  remind_after_hours: 24
```

- 프로젝트의 GitHub 저장소 이름, 채널 ID는 [미결]이 아니라 실제 값 확인이 필요한 항목이다 (맥에서 채움)
- 로더 규칙 (`bot/config.py`, 2026-10-07 구현)
  - 모르는 키는 오류로 처리한다 (오타를 조용히 무시하지 않기 위해)
  - `paths`의 `vault_projects`는 필수, 나머지와 `cli`·`limits`는 위 값이 기본값이다. 경로는 절대 경로이거나 `~`로 시작해야 한다
  - `base_branch`는 생략하면 `develop`이고, `main`은 거부한다 (9.5)
  - `test`는 문자열이면 셸 문법(`shlex`)으로 인자 목록으로 나눠 저장하고, 실행은 셸 없이 한다 (2.1). 목록으로 적어도 된다
  - 프로젝트 키는 영문 소문자·숫자·`-`, 포럼 채널 ID는 프로젝트끼리 겹치면 안 된다
  - 오류 메시지에는 위치와 이유만 담고 값은 넣지 않는다

### 9.2 `.env` (커밋 금지)

| 키 | 내용 |
|---|---|
| `DISCORD_TOKEN` | 봇 토큰 |
| `DISCORD_GUILD_ID` | 비공개 서버 ID |
| `ZERO_USER_ID` | 명령 권한자 |
| `OPS_CHANNEL_ID` | #zerosync-ops |

웹훅 URL은 두지 않는다. 봇이 시작할 때 찾거나 만든다 (6.1, Q6).

실제 환경변수가 있으면 `.env`보다 우선한다. `.env` 파일은 없어도 되지만 네 키는 어느 쪽에든 있어야 한다. ID는 숫자 문자열로 검증하고, 토큰은 `SecretStr`로 담아 출력·repr에 드러나지 않게 한다. 예시는 `.env.example`.

### 9.3 실행
- 개발: `tmux` 안에서 `caffeinate -is python -m bot`
- 운영: `deploy/com.zerosync.orchestrator.plist`를 `~/Library/LaunchAgents/`에 두고 `launchctl bootstrap gui/$(id -u) <plist>`. `RunAtLoad`, `KeepAlive`, 로그 경로, PATH 지정
- LaunchDaemon(root)으로 실행하지 않는다. CLI 구독 로그인이 사용자 계정에 있기 때문이다
- 운영 맥: 전원 상시 연결, 시스템 잠자기 방지, 상시 켜 두는 맥 한 대에서만 실행

### 9.4 사전 준비 체크리스트
- Python 3.11+, git, `gh`(인증), Xcode(시뮬레이터 런타임 포함), `claude`·`codex` CLI(구독 로그인)
- 각 앱 저장소에서 CLI를 한 번 수동 실행해 폴더 신뢰·권한 질문 처리. 2026-10-10 시험 호출에서는 신뢰 처리하지 않은 임시 폴더에서도 `claude -p`, `codex exec`가 질문 없이 실행됐다. 실제 저장소에서 다시 확인한다
- Discord: 비공개 서버, 포럼 채널, 봇 초대(Send Messages, Send Messages in Threads, Create Public Threads, Read Message History, Manage Webhooks, Manage Threads), Message Content Intent
- GitHub: 앱 저장소 Merge commit만 허용, head 브랜치 자동 삭제 켬 (트러블슈팅 2026-10-05 참고)

### 9.5 보안 [확정]
- 봇은 사실상 원격 셸이다. Zero의 ID 외 입력 무시, 비공개 서버·채널에서만 운영
- 금지: main 접근, develop 직접 push, force push, merge, `.env` 수정, 지정 저장소·볼트 허용 경로 밖 쓰기
- 로그와 Discord 게시물에 토큰이 섞이지 않도록 출력 전 마스킹 [제안]

---

## 10. 검증 필요 목록

맥에서 Claude Code로 개발을 시작하기 전후에 확인한다. 결과는 개발 일지와 이 절에 기록한다.

| # | 항목 | 확인 방법 | 영향 | 결과 |
|---|---|---|---|---|
| V1 | `claude -p`의 JSON 출력·스키마 강제 옵션, 세션 ID 반환 | `claude --help`, 짧은 호출 | 5.2, 2.1 | 확인 (2026-10-10, v2.1.285): `--output-format json`, `--json-schema`, `session_id`, `--resume` 동작 |
| V2 | `codex exec`의 출력 스키마 지정·마지막 메시지 파일 출력 옵션 | `codex exec --help` | 5.2 | 확인 (2026-10-10, v0.161.0): `--output-schema`, `-o`, read-only 샌드박스 쓰기 차단 |
| V3 | Claude 쓰기 단계의 허용·금지 도구 지정 방식 | 공식 문서, 시험 호출 | 5.2 권한 | 확인 (2026-10-10): `--allowedTools`·`--disallowedTools`·`--permission-mode`·`--permission-prompts none` |
| V4 | Codex read-only 샌드박스에서 `xcodebuild` 실패 여부 | 시험 호출 | 1.7 (봇이 테스트 실행하는 근거) |  |
| V5 | 웹훅 메시지의 silent(알림 억제) 지원 | 시험 게시 | 2.5 멘션 규칙 |  |
| V6 | 개인 private 저장소에서 브랜치 보호(rulesets) 사용 가능 여부 | GitHub 설정 | 4.7 |  |
| V7 | `gh` 인증 계정의 Issue·PR 쓰기 권한 | `gh auth status`, 시험 Issue | 1.8, 1.9 |  |
| V8 | 볼트 루트가 git 저장소인지, iCloud 동기화 중 쓰기 안정성 | `git -C <볼트> status` | 3.10 |  |
| V9 | xcodebuild CoreDevice 오류(`_XPCTypeBool`) 해결 | `xcodebuild test` | 1.7 전체. Phase 4 차단 요인 |  |
| V10 | launchd 환경에서 CLI 실행(PATH, 키체인 접근) | plist로 시험 실행 | 9.3 |  |

---

## 11. 미결 사항

2026-10-07에 Zero가 Q1~Q11을 모두 결정했다. Q9를 빼면 이 문서의 제안대로다.

| # | 질문 | 결정 |
|---|---|---|
| Q1 | 설계 요약 JSON의 나머지 필드 구성, 대상 기능이 여러 개일 수 있는가 | 5.4 표. 대상 기능은 1개로 시작 |
| Q2 | 테스트 실패 재시도 한도 | 2회 초과 시 NEEDS_HUMAN |
| Q3 | 설계 승인 생략 옵션 (초안의 "승인 지점 2, 생략 가능") | 두지 않음. 운영 규약 1.5대로 항상 `/approve` |
| Q4 | NEEDS_HUMAN에서 재개하는 방법 | `/resume`. 카운터는 유지하고 한도를 1회만 늘림 |
| Q5 | 토론 라운드 기본값 | `/debate`로만 실행 (사용량 절약) |
| Q6 | 웹훅 URL을 `.env`에 둘지, 봇이 만들지 | 봇이 시작 시 찾거나 만든다 |
| Q7 | `/revise`를 설계 승인 단계에서도 쓸지 | 쓴다 (운영 규약 3.3의 "설계 수정 요청"을 명령으로) |
| Q8 | 봇 재시작 시 실행 중이던 작업 처리 | NEEDS_HUMAN으로 전환하고 알림 |
| Q9 | ZeroSync 저장소 자체의 기준 브랜치 표기 정리 | 저장소는 반영 완료: AGENTS.md와 운영 규약 4.1이 develop 기준 (PR #2). claude.ai 프로젝트 지침은 Zero가 직접 수정 |
| Q10 | Obsidian 동기화 방식과 에이전트별 폴더 분리 (초안 10-4) | 운영 규약 3.4로 대부분 정해짐. 동기화는 iCloud 유지 |
| Q11 | 저장소가 공개(public)이므로 `projects.yaml`(9.1)의 Discord 채널 ID, 로컬 경로를 커밋할지 | 실제 값 파일은 커밋하지 않고 `projects.example.yaml`(값 비움)만 둔다 |

---

## 12. 구현 순서 (로드맵)

### 12.1 Phase

| Phase | 내용 | 상태 |
|---|---|---|
| 0 | 문서 정비: 운영 규약, ADR-005, AGENTS.md, 스키마, SPEC.md | 진행 중 (SPEC.md가 마지막) |
| 1 | MVP: 포럼 게시글 감지 → Beta·Alpha 의견 병렬 게시 | 미시작 |
| 2 | 워크플로: 상태 머신 전체, 승인 명령, 리뷰 루프, 테스트 실행, Issue·PR, /stop | 미시작 |
| 3 | 운영화: 멀티 프로젝트, 빌드 락, launchd, /ping, 재멘션, 볼트·DOC_SYNC | 미시작 |
| 4 | 파일럿: 가게씨에서 한 사이클 완주 | 미시작 |
| 5 | 확장: 제이데이 → 오롯 | 미시작 |
| 6 (선택) | SwiftUI 메뉴바 대시보드 (SQLite 읽기 전용) | 미시작 |

### 12.2 Phase 1 스레드 분할 [제안]
각 스레드는 develop에서 브랜치를 만들고 draft PR 하나로 끝낸다. 시작 전 범위를 제안하고 Zero의 승인을 받는다.

1. `feat/0-agent-runner` — `AgentRunner` 인터페이스, `FakeAgentRunner`, 자식 프로세스 실행(타임아웃·취소, 실행 로그 저장)
   - CLI 러너는 CLI 설치 후 별도 스레드로 분리했다 (2026-10-07 Zero 승인): 이 맥에 `claude`·`codex`가 없어 V1~V3을 확인할 수 없었다
1-2. `feat/0-cli-runners` — `ClaudeCliRunner`·`CodexCliRunner`. V1~V3 확인 후 명령 형식 결정. 실제 CLI 호출은 수동 스모크 스크립트(`scripts/smoke_cli.py`)로만 확인 (2026-10-10 구현)
2. `feat/0-store-state` — SQLite 스키마·저장소, 상태 enum과 OPINIONS 범위의 전이 규칙 (`/decide` → DESIGNING, 모든 상태의 `/stop` 포함). 효과는 타입만 정의하고 실행은 엔진 스레드에서
3. `feat/0-config` — `projects.yaml`, `.env` 로더, 단일 인스턴스 락. 진입점은 설정 로드와 락까지만 연결 (YAML은 PyYAML, `.env`는 직접 파싱: 2026-10-07 Zero 결정)
4. 두 스레드로 나눴다 (2026-10-10 Zero 승인)
   - 4-1. `feat/0-opinion-engine` — `ChatIO` 인터페이스, 의견·반박 프롬프트, render, 멘션 규칙, OPINIONS 단계 엔진(병렬 호출, 형식 오류 재요청, /stop 취소). `/decide`는 결정 기록과 안내까지만(Issue·볼트·설계는 Phase 2) (2026-10-10 구현)
   - 4-2. `feat/0-discord-io` — discord.py, 포럼 게시글 감지, Zero 외 입력 무시, 슬래시 명령, 웹훅 게시(V5), 운영 채널, 진입점 연결. 실제 `.env`·채널 ID 필요
5. `chore/0-launchd` — plist와 실행 문서 (Phase 3로 미뤄도 됨)

### 12.3 테스트 전략
- 단위: 전이 규칙, 멘션 판정, 브랜치 이름·push 보호, 커밋 메시지 정규식, 볼트 허용 경로, render 출력, 프롬프트 렌더링
- 통합: 모든 외부 의존(Agent, ChatIO, GitHub, Git, Vault, TestRunner, Clock)을 가짜로 바꾼 채 한 사이클 전체를 시뮬레이션하는 테스트 1개 이상
- 실제 CLI, Discord, GitHub는 CI에서 호출하지 않는다. 수동 스모크 스크립트(`scripts/`)로만 확인한다
- 완료 조건: `pytest`, `ruff check .`, `ruff format --check .` 통과 (AGENTS.md)

---

## 부록 A. 초안(2026-09-30) 대비 바뀐 점

| 항목 | 초안 | 현재 | 근거 |
|---|---|---|---|
| Alpha/Beta 매핑 | 미결 | Alpha = Codex, Beta = Claude, 봇은 인격 없음 | 운영 규약 1.2 |
| 테스트 재실행 | Codex | 봇이 실행, Codex는 결과로 판정 | 운영 규약 1.7 |
| 작업 브랜치 | `claude/<작업명>` | `<type>/<Issue번호>-<slug>`, develop 기준 | 운영 규약 4.2 |
| 작업 시작 | `/idea` | 포럼 게시글 작성 | 이 문서 3.1 |
| 승인 지점 | 3개 (설계 승인 생략 가능) | 설계 승인, 최종 merge, 문서 반영 승인 | 운영 규약 1.5, 3.9 |
| 문서 반영 | 없음 | DOC_SYNC 단계 추가 | 운영 규약 3.9 |
| 에이전트 출력 | 첫 줄 판정 문자열 | JSON 스키마 + pydantic 검증 | 운영 규약 2.1 |
| CLAUDE.md 규칙 | 수정 필요 | AGENTS.md 기준으로 재작성 완료 | PR #2 |
| v1 Xcode 프로젝트 | 처리 미정 | `menubar/`로 이동 | PR #3·#4 |

## 부록 B. 검토했으나 채택하지 않은 대안

| 대안 | 미채택 이유 |
|---|---|
| Slack | 무료 플랜 기록 90일 제한. 팀 도입 시 재검토 |
| 봇 2개가 서로의 메시지에 반응 | 흐름 제어 주체가 없어 무한 루프 위험 |
| 공식 Slack 연동(@Claude, @Codex) | 클라우드에서 실행되어 로컬 저장소·시뮬레이터에 접근 불가 |
| Claude Code의 Discord 채널 기능 | 사람 한 명과 세션 하나의 용도. 보조 지시 채널로만 활용 가능 |
| 서드파티 브릿지 | 상태 머신과 승인 지점을 직접 통제하기 위해 자체 구현 |
| HTTP Interactions Endpoint 방식 봇 | 맥은 외부에서 접속할 수 없음. Gateway 방식 사용 |
