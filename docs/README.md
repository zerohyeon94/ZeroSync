# Zero-Alpha-Beta 개발 문서

> "세 개의 인격이 하나의 비서를 이룬다."
> macOS 메뉴바 기반 AI 비서 — Zero(ENFJ) · Alpha(INTJ) · Beta(ISFJ)

---

## 문서 구조

| 폴더 | 목적 | 언제 사용 |
|------|------|-----------|
| [CONCEPT.md](CONCEPT.md) | 프로젝트 전체 기획서 | 방향 흔들릴 때 |
| [개발 일지/](개발%20일지/README.md) | 날짜별 작업 기록 | 매일 개발 후 |
| [트러블슈팅/](트러블슈팅/README.md) | 문제 → 원인 → 해결 기록 | 버그 해결 직후 |
| [아키텍처 결정/](아키텍처%20결정/README.md) | 기술 선택 근거 (ADR) | 중요한 기술 결정 시 |
| [기능 개발/](기능%20개발/README.md) | 기능별 설계 및 구현 노트 | 기능 개발 중/후 |
| [개선 방향/](개선%20방향/README.md) | 백로그 및 아이디어 | 개선 아이디어 생길 때 |
| [회고/](회고/README.md) | 주간/마일스톤 회고 | Phase 완료 시 |

---

## 현재 개발 상태

**Phase 1 진행 중** (기반 구축)

| 항목 | 상태 |
|------|------|
| Electron 메뉴바 기본 구조 | ✅ 완료 |
| Claude API 연동 (Alpha/Beta 시스템 프롬프트) | 🔄 진행 중 |
| 기본 채팅 UI (페르소나 전환) | 🔄 진행 중 |
| 대화 히스토리 로컬 저장 | ⬜ 미시작 |

---

## 기술 스택

- **플랫폼**: Electron 34 + electron-vite
- **UI**: React 18 + TypeScript
- **AI**: Claude API (claude-sonnet-4-6) — `@anthropic-ai/sdk`
- **저장**: electron-store (로컬)
- **패키징**: electron-builder (.dmg)
