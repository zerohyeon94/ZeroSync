# ZeroSync 개발 문서

> Discord 기반 멀티 에이전트 오케스트레이터 (v2)
> Zero(ENFJ)가 판단하고, Beta · Claude(ISFJ)와 Alpha · Codex(INTJ)가 제안·구현·리뷰하며, 봇이 전달하고 기록한다.

---

## 기준 문서

| 문서 | 내용 | 상태 |
|------|------|------|
| [운영-규약.md](운영-규약.md) | 역할·권한, Discord 대화 형태, 기록 위치, GitHub 규칙 | 확정 (2026-10-05) |
| SPEC.md | 봇 설계 (명령어, 상태 머신, 구성 요소) | 추가 예정 |
| [ADR-005](아키텍처%20결정/ADR-005-Discord-오케스트레이터-전환.md) | v2 전환 결정 | 확정 |
| [CONCEPT.md](CONCEPT.md) | v1 메뉴바 앱 기획서 | v1 한정, SPEC.md로 대체 예정 |

SPEC.md와 운영 규약이 다르면 운영 규약을 따른다.

---

## 문서 구조

| 폴더 | 목적 | 언제 사용 |
|------|------|-----------|
| [개발 일지/](개발%20일지/README.md) | 봇 자체 개발의 날짜별 작업 기록 | 매일 개발 후 |
| [트러블슈팅/](트러블슈팅/README.md) | 문제 → 원인 → 해결 기록 | 버그 해결 직후 |
| [아키텍처 결정/](아키텍처%20결정/README.md) | 기술 선택 근거 (ADR) | 중요한 기술 결정 시 |
| [기능 개발/](기능%20개발/README.md) | 기능별 설계 및 구현 노트 | 기능 개발 중/후 |
| [개선 방향/](개선%20방향/README.md) | 백로그 및 아이디어 | 개선 아이디어 생길 때 |
| [회고/](회고/README.md) | Phase 완료 시 회고 | Phase 완료 시 |

이 폴더는 ZeroSync 저장소 자체의 개발 기록이다. 봇이 관리하는 앱 저장소의 설계 문서(`docs/설계/`)와 Obsidian 볼트 기록은 여기에 두지 않는다 (운영 규약 3장).

---

## 현재 개발 상태

**Phase 0 진행 중** (v2 문서 정비)

| 항목 | 상태 |
|------|------|
| 운영 규약 확정 및 저장소 반영 | 완료 |
| ADR-005 (v2 전환) | 완료 |
| CLAUDE.md, AGENTS.md 봇 개발 기준으로 재작성 | 완료 |
| SPEC.md 저장소 반영 | 미시작 |
| v1 Xcode 프로젝트를 `menubar/`로 이동 | 완료 |
| 봇 골격 (`bot/`, pytest·ruff 설정) | 완료 |
| 에이전트 출력 스키마 (의견, 리뷰 판정) | 완료 |
| 설계 요약 스키마 (change_type, target_feature, slug) | 완료 (나머지 필드는 SPEC.md 대기) |
| 봇 기능 구현 (SQLite, 에이전트 호출, discord_io) | 미시작 |

---

## 기술 스택

v2 봇
- **언어**: Python 3.11+
- **검증**: pydantic (에이전트 출력 JSON 스키마)
- **저장**: SQLite (봇 상태, 에이전트 출력 원본)
- **인터페이스**: Discord (`bot/discord_io/` 계층 뒤에 격리)
- **에이전트**: Claude CLI, Codex CLI
- **도구**: pytest, ruff

v1 메뉴바 앱 (보류, `menubar/`)
- Swift + SwiftUI (macOS 14+), Ollama 로컬 LLM, SwiftData
