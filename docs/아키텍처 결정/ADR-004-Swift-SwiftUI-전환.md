# ADR-004 — macOS 앱 프레임워크를 Electron에서 Swift + SwiftUI로 전환

> 날짜: 2026-04-29 | 상태: 확정 | 대체: ADR-001

---

## 결정

macOS 메뉴바 AI 비서 앱을 **Swift + SwiftUI (macOS 14+)** 네이티브 앱으로 구현한다.
기존 ADR-001에서 결정한 Electron 방식을 폐기한다.

## 맥락

- Electron 초기 세팅 후, 메뉴바 앱 특성상 네이티브 성능과 경량화가 더 중요하다고 판단
- macOS 전용 앱이므로 크로스 플랫폼 이점이 없음
- SwiftUI의 `MenuBarExtra` API가 macOS 13+에서 충분히 성숙해짐

## 선택지

| 옵션 | 장점 | 단점 |
|------|------|------|
| Electron (ADR-001) | 웹 기술 재사용, Node.js SDK 그대로 사용 | 앱 크기 100MB+, 메모리 idle 200MB+, 배터리 소모 |
| **Swift + SwiftUI** | 네이티브 성능, 앱 크기 10MB 이하, 배터리 효율, Xcode 직접 배포 | Claude API HTTP 클라이언트 직접 구현 필요 |
| Tauri | Electron보다 가볍고 빠름 | Rust 필요, macOS 메뉴바 지원 초기 단계 |

## 근거

- macOS 전용 앱 → 네이티브 스택이 최적
- `MenuBarExtra` (macOS 13+) : SwiftUI에서 메뉴바 앱을 선언적으로 구현 가능
- SwiftData : 대화 히스토리 로컬 저장을 별도 라이브러리 없이 처리
- `URLSession` : Claude API는 HTTP REST → Swift 표준 라이브러리로 충분
- Xcode Archive + notarization : 공식 배포 파이프라인 그대로 사용

## 구현 방식

```swift
// 메뉴바 상주: MenuBarExtra
MenuBarExtra("ZeroSync", systemImage: "...") {
    MenuBarView()
}
.menuBarExtraStyle(.window)

// Claude API: URLSession + async/await
let (data, _) = try await URLSession.shared.data(for: request)

// 로컬 저장: SwiftData
@Model class Message { ... }
```

## 트레이드오프

- Claude API Swift 클라이언트를 직접 구현해야 함 (공식 Swift SDK 없음)
- Swift/SwiftUI 학습 곡선이 있으나, macOS 전용이므로 장기적으로 유리
- 향후 Apple Intelligence / FoundationModels 연동 시 네이티브 스택이 더 유리
