# ADR-001 — macOS 앱 프레임워크로 Electron 선택

> 날짜: 2026-04-28 | 상태: **폐기** (ADR-004로 대체됨)

---

## 결정

macOS 메뉴바 AI 비서 앱을 **Electron + Vite + React + TypeScript**로 구현한다.

## 맥락

- macOS 네이티브 메뉴바 앱이 필요
- Claude API(HTTP 요청) 연동 필수
- React 기반 UI를 선호 (기존 웹 개발 경험 활용)
- 빠른 프로토타이핑이 우선

## 선택지

| 옵션 | 장점 | 단점 |
|------|------|------|
| **Electron** | 웹 기술 그대로 사용, Claude API 연동 쉬움 | 앱 크기 큼 (100MB+), 메모리 사용량 높음 |
| Swift (AppKit) | 네이티브 성능, 메뉴바 API 직접 사용 | Swift 학습 곡선, Claude API 별도 구현 필요 |
| Tauri | Electron보다 가볍고 빠름 | Rust 필요, macOS 메뉴바 지원 초기 단계 |

## 근거

- 웹 기술(React/TypeScript)로 빠르게 프로토타입 가능
- Claude API는 HTTP 기반 → Node.js 환경에서 SDK 그대로 사용
- `electron-vite`로 HMR 개발 환경 설정이 간단
- macOS 메뉴바 트레이 API는 Electron이 가장 성숙함

## 트레이드오프

- 앱 크기: 최소 80~150MB (배포 시 문제될 수 있음)
- RAM 사용량: Chromium 기반이라 idle 상태에서도 200MB+
- 향후 Tauri로 마이그레이션 고려 가능 (Phase 3 이후)
