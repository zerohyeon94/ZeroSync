import Foundation
import Testing
@testable import ZeroSync

@MainActor
struct ActivityMonitorTests {

    final class FakeSource: ActivitySource {
        var next: ActivitySnapshot?
        func snapshot() -> ActivitySnapshot? { next }
    }

    @Test func 스냅샷을_분류해서_현재_활동으로_노출() {
        let source = FakeSource()
        let monitor = ActivityMonitor(source: source, classifier: ActivityClassifier(rules: .default))

        source.next = ActivitySnapshot(appName: "Xcode", windowTitle: "Pet.swift", idleSeconds: 2, date: .now)
        monitor.poll()
        #expect(monitor.current?.category == .productive)

        source.next = ActivitySnapshot(appName: "Safari", windowTitle: "재밌는 영상 - YouTube", idleSeconds: 1, date: .now)
        monitor.poll()
        #expect(monitor.current?.category == .distraction)
    }

    @Test func 유휴_상태는_카테고리를_바꾸지_않고_플래그만_켠다() {
        // 강의 시청·문서 읽기처럼 입력이 없어도 학습일 수 있음 — 즉시 딴짓 판정 금지
        let source = FakeSource()
        let monitor = ActivityMonitor(source: source, classifier: ActivityClassifier(rules: .default))
        source.next = ActivitySnapshot(appName: "Xcode", windowTitle: nil, idleSeconds: 400, date: .now)
        monitor.poll()
        #expect(monitor.current?.category == .productive)
        #expect(monitor.current?.isIdle == true)
    }
}
