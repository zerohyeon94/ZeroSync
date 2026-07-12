import AppKit
import ApplicationServices
import Observation

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

    /// 마지막 하드웨어 키보드·마우스 입력 이후 경과 시간 (권한 불필요, 입력 내용은 수집하지 않음)
    static func idleSeconds() -> TimeInterval {
        // kCGAnyInputEventType: 모든 입력 이벤트 종류를 포괄하는 특수값 (~0)
        CGEventSource.secondsSinceLastEventType(.hidSystemState, eventType: CGEventType(rawValue: ~0)!)
    }
}

/// 분류가 끝난 현재 활동
struct ClassifiedActivity: Sendable {
    let appName: String
    let windowTitle: String?
    let category: ActivityCategory
    let isIdle: Bool
    let date: Date
}

/// 5초 폴링 + 앱 전환 이벤트로 현재 활동을 갱신한다.
@MainActor
@Observable
final class ActivityMonitor {
    static let shared = ActivityMonitor(source: SystemActivitySource(),
                                        classifier: ActivityClassifier(rules: .default))
    /// 이 시간 이상 입력이 없으면 유휴로 표시 (판정은 바꾸지 않음)
    static let idleThreshold: TimeInterval = 300

    private(set) var current: ClassifiedActivity?

    private let source: ActivitySource
    private let classifier: ActivityClassifier
    private var timer: Timer?
    private var appSwitchObserver: (any NSObjectProtocol)?

    init(source: ActivitySource, classifier: ActivityClassifier) {
        self.source = source
        self.classifier = classifier
    }

    func start() {
        guard timer == nil else { return }
        poll()
        let timer = Timer(timeInterval: 5, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.poll() }
        }
        RunLoop.main.add(timer, forMode: .common)
        self.timer = timer

        appSwitchObserver = NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didActivateApplicationNotification, object: nil, queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated { self?.poll() }
        }
    }

    func stop() {
        timer?.invalidate()
        timer = nil
        if let appSwitchObserver {
            NSWorkspace.shared.notificationCenter.removeObserver(appSwitchObserver)
            self.appSwitchObserver = nil
        }
    }

    func poll() {
        guard let snap = source.snapshot() else { return }
        current = ClassifiedActivity(
            appName: snap.appName,
            windowTitle: snap.windowTitle,
            category: classifier.classify(appName: snap.appName, windowTitle: snap.windowTitle),
            isIdle: snap.idleSeconds >= Self.idleThreshold,
            date: snap.date
        )
    }
}
