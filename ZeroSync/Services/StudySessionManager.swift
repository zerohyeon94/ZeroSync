import Foundation
import Observation
import SwiftData

/// 학습 세션 수명주기 관리 — 시작/종료, 5초 틱으로 현재 활동을 세션에 누적, SwiftData 저장
@MainActor
@Observable
final class StudySessionManager {
    static let shared = StudySessionManager(monitor: ActivityMonitor.shared)

    private(set) var activeSession: StudySession?
    private(set) var lastSession: StudySession?

    private let monitor: ActivityMonitor
    private var context: ModelContext?
    private var timer: Timer?
    private var lastTick: Date = .now

    init(monitor: ActivityMonitor) {
        self.monitor = monitor
    }

    /// 앱 시작 시 한 번 호출 — 저장소 연결 + 마지막 세션 복원
    func configure(context: ModelContext) {
        self.context = context
        loadLastSession()
    }

    func startSession(now: Date = .now) {
        guard activeSession == nil else { return }
        let session = StudySession(startedAt: now)
        context?.insert(session)
        activeSession = session
        lastTick = now

        let timer = Timer(timeInterval: 5, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.tick() }
        }
        RunLoop.main.add(timer, forMode: .common)
        self.timer = timer
    }

    func endSession(now: Date = .now) {
        guard let session = activeSession else { return }
        tick(now: now)                    // 마지막 구간까지 누적
        session.endedAt = now
        try? context?.save()
        lastSession = session
        activeSession = nil
        timer?.invalidate()
        timer = nil
    }

    /// 직전 틱 이후 경과 시간을 현재 활동 카테고리에 누적
    func tick(now: Date = .now) {
        guard let session = activeSession else { return }
        let dt = now.timeIntervalSince(lastTick)
        lastTick = now
        guard let activity = monitor.current else { return }   // 관측 없으면 이번 구간은 버림
        session.accumulate(dt: dt, category: activity.category, isIdle: activity.isIdle)
    }

    /// 가장 최근에 끝난 세션을 불러온다 (앱 재시작 후 리포트 표시용)
    private func loadLastSession() {
        guard let context else { return }
        var descriptor = FetchDescriptor<StudySession>(
            predicate: #Predicate { $0.endedAt != nil },
            sortBy: [SortDescriptor(\.startedAt, order: .reverse)]
        )
        descriptor.fetchLimit = 1
        lastSession = (try? context.fetch(descriptor))?.first
    }
}
