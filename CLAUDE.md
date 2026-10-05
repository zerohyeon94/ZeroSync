# Zero-Alpha-Beta

맥 메뉴바 기반 AI 비서 앱 (Swift + SwiftUI)

## 캐릭터
- 제로(사용자): ENFJ — 비전 제시
- 알파(Alpha): ESTP — 행동파 반항아, 즉흥적 현실주의자
- 베타(Beta): ISFJ — 외유내강 수호자, 감정 중재자

## 기술 스택
- Swift + SwiftUI (macOS 14+)
- Ollama 로컬 LLM (기본 qwen3:14b) — localhost:11434, URLSession 기반
- 로컬 지식 연동 — Obsidian vault·Developer 폴더 md 검색 주입 (보안 범위 북마크)
- SwiftData (로컬 저장)
- Xcode Archive → notarized .dmg (배포)

## 규칙
- 응답: 반드시 한국어
- 이모지 사용 금지
- 확인 없이 git push 금지

## 문서 구조
- `docs/README.md` — 문서 전체 인덱스
- `docs/개발 일지/` — 날짜별 작업 기록 (매일 작성)
- `docs/트러블슈팅/` — 문제 → 원인 → 해결 기록
- `docs/아키텍처 결정/` — ADR (기술 선택 근거)
- `docs/기능 개발/` — 기능별 설계 및 구현 노트
- `docs/개선 방향/` — 백로그 및 아이디어
- `docs/회고/` — Phase 완료 시 회고

## 개발 일지 작성 원칙
개발 후 `docs/개발 일지/YYYY-MM-DD.md` 파일에 기록:
1. 오늘 한 것
2. 막힌 것 / 발견한 것
3. 내일 할 것
