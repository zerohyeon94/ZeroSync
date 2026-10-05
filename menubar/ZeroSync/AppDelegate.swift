import AppKit

class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        DesktopPetManager.shared.applyEnabledSetting()

        // 활동 감지 시작 — 손쉬운 사용 권한이 없으면 시스템 설정 유도 다이얼로그 표시
        // (권한 거부 시에도 앱 이름·유휴 시간만으로 축소 모드 동작)
        _ = SystemActivitySource.isAccessibilityTrusted(promptIfNeeded: true)
        ActivityMonitor.shared.start()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        false
    }
}
