import AppKit
import ApplicationServices

/// 한 시점의 사용자 활동 관측값
struct ActivitySnapshot: Sendable {
    let appName: String
    let windowTitle: String?
    let idleSeconds: TimeInterval
    let date: Date
}

/// 시스템 관측 추상화 — 테스트에서 가짜 소스로 대체
protocol ActivitySource {
    @MainActor func snapshot() -> ActivitySnapshot?
}

/// 실제 시스템 API 구현
@MainActor
final class SystemActivitySource: ActivitySource {

    /// 손쉬운 사용 권한 확인. promptIfNeeded=true면 시스템 설정 유도 다이얼로그 표시
    static func isAccessibilityTrusted(promptIfNeeded: Bool = false) -> Bool {
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: promptIfNeeded] as CFDictionary
        return AXIsProcessTrustedWithOptions(options)
    }

    func snapshot() -> ActivitySnapshot? {
        guard let app = NSWorkspace.shared.frontmostApplication,
              let name = app.localizedName else { return nil }
        return ActivitySnapshot(
            appName: name,
            windowTitle: Self.isAccessibilityTrusted() ? focusedWindowTitle(pid: app.processIdentifier) : nil,
            idleSeconds: Self.idleSeconds(),
            date: .now
        )
    }

    /// 전면 앱의 포커스된 창 제목 (손쉬운 사용 권한 필요, 샌드박스 해제 필요)
    private func focusedWindowTitle(pid: pid_t) -> String? {
        let appElement = AXUIElementCreateApplication(pid)
        var window: CFTypeRef?
        guard AXUIElementCopyAttributeValue(appElement, kAXFocusedWindowAttribute as CFString, &window) == .success,
              let window else { return nil }
        guard CFGetTypeID(window) == AXUIElementGetTypeID() else { return nil }
        let windowElement = unsafeBitCast(window, to: AXUIElement.self)
        var title: CFTypeRef?
        guard AXUIElementCopyAttributeValue(windowElement, kAXTitleAttribute as CFString, &title) == .success else { return nil }
        return title as? String
    }

    /// 마지막 키보드·마우스 입력 이후 경과 시간 (권한 불필요, 입력 내용은 수집하지 않음)
    static func idleSeconds() -> TimeInterval {
        let types: [CGEventType] = [.keyDown, .mouseMoved, .leftMouseDown, .scrollWheel]
        return types
            .map { CGEventSource.secondsSinceLastEventType(.combinedSessionState, eventType: $0) }
            .min() ?? 0
    }
}
