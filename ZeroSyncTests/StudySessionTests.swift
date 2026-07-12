import Foundation
import Testing
@testable import ZeroSync

struct StudySessionTests {

    @Test func 카테고리별로_시간이_누적된다() {
        let session = StudySession(startedAt: .now)
        session.accumulate(dt: 5, category: .productive, isIdle: false)
        session.accumulate(dt: 3, category: .distraction, isIdle: false)
        session.accumulate(dt: 2, category: .neutral, isIdle: false)
        #expect(session.productiveSeconds == 5)
        #expect(session.distractionSeconds == 3)
        #expect(session.neutralSeconds == 2)
    }

    @Test func 유휴는_카테고리와_무관하게_유휴로_누적된다() {
        let session = StudySession(startedAt: .now)
        session.accumulate(dt: 10, category: .productive, isIdle: true)
        #expect(session.idleSeconds == 10)
        #expect(session.productiveSeconds == 0)
    }

    @Test func 집중율은_유휴를_제외한_활동_중_생산_비율() {
        let session = StudySession(startedAt: .now)
        session.accumulate(dt: 6, category: .productive, isIdle: false)
        session.accumulate(dt: 2, category: .distraction, isIdle: false)
        session.accumulate(dt: 100, category: .neutral, isIdle: true)   // 유휴는 분모 제외
        #expect(session.focusRate == 0.75)
    }

    @Test func 활동이_없으면_집중율은_0() {
        let session = StudySession(startedAt: .now)
        #expect(session.focusRate == 0)
    }

    @Test func 총_시간은_시작부터_종료까지() {
        let t0 = Date(timeIntervalSince1970: 1_000)
        let session = StudySession(startedAt: t0)
        session.endedAt = t0.addingTimeInterval(90)
        #expect(session.totalSeconds == 90)
    }
}
