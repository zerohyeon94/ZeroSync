import Foundation
import SwiftData
import Testing
@testable import ZeroSync

@MainActor
struct StudySessionManagerTests {

    final class FakeSource: ActivitySource {
        var next: ActivitySnapshot?
        func snapshot() -> ActivitySnapshot? { next }
    }

    /// 테스트 환경 — container를 함께 보유해 수명 유지 (해제되면 mainContext 사용 시 크래시)
    struct Env {
        let manager: StudySessionManager
        let monitor: ActivityMonitor
        let source: FakeSource
        let container: ModelContainer
    }

    /// 인메모리 컨테이너 + 가짜 소스로 매니저 구성
    private func makeManager() throws -> Env {
        let source = FakeSource()
        let monitor = ActivityMonitor(source: source, classifier: ActivityClassifier(rules: .default))
        let container = try ModelContainer(
            for: StudySession.self,
            configurations: ModelConfiguration(isStoredInMemoryOnly: true)
        )
        let manager = StudySessionManager(monitor: monitor)
        manager.configure(context: container.mainContext)
        return Env(manager: manager, monitor: monitor, source: source, container: container)
    }

    private func snapshot(app: String, title: String?, idle: TimeInterval = 0) -> ActivitySnapshot {
        ActivitySnapshot(appName: app, windowTitle: title, idleSeconds: idle, date: .now)
    }

    @Test func 세션_시작_전에는_활성_세션이_없다() throws {
        let env = try makeManager()
        #expect(env.manager.activeSession == nil)
    }

    @Test func 틱마다_현재_활동_카테고리에_시간이_누적된다() throws {
        let env = try makeManager()
        let t0 = Date(timeIntervalSince1970: 1_000)
        env.manager.startSession(now: t0)

        env.source.next = snapshot(app: "Xcode", title: "Pet.swift")
        env.monitor.poll()
        env.manager.tick(now: t0.addingTimeInterval(5))
        #expect(env.manager.activeSession?.productiveSeconds == 5)

        env.source.next = snapshot(app: "Safari", title: "재밌는 영상 - YouTube")
        env.monitor.poll()
        env.manager.tick(now: t0.addingTimeInterval(12))
        #expect(env.manager.activeSession?.distractionSeconds == 7)
    }

    @Test func 유휴_틱은_유휴_시간으로_누적된다() throws {
        let env = try makeManager()
        let t0 = Date(timeIntervalSince1970: 1_000)
        env.manager.startSession(now: t0)
        env.source.next = snapshot(app: "Xcode", title: nil, idle: 400)
        env.monitor.poll()
        env.manager.tick(now: t0.addingTimeInterval(5))
        #expect(env.manager.activeSession?.idleSeconds == 5)
        #expect(env.manager.activeSession?.productiveSeconds == 0)
    }

    @Test func 종료하면_마지막_세션으로_저장되고_활성_세션은_사라진다() throws {
        let env = try makeManager()
        let t0 = Date(timeIntervalSince1970: 1_000)
        env.manager.startSession(now: t0)
        env.source.next = snapshot(app: "Xcode", title: nil)
        env.monitor.poll()
        env.manager.endSession(now: t0.addingTimeInterval(30))

        #expect(env.manager.activeSession == nil)
        #expect(env.manager.lastSession?.endedAt != nil)
        #expect(env.manager.lastSession?.productiveSeconds == 30)   // 종료 시 마지막 구간까지 누적
        #expect(env.manager.lastSession?.totalSeconds == 30)
    }

    @Test func 이중_시작은_무시된다() throws {
        let env = try makeManager()
        let t0 = Date(timeIntervalSince1970: 1_000)
        env.manager.startSession(now: t0)
        let first = env.manager.activeSession
        env.manager.startSession(now: t0.addingTimeInterval(10))
        #expect(env.manager.activeSession === first)
    }
}
