import Foundation
import SwiftData

/// 학습 세션 한 번의 기록. 카테고리별 누적 시간만 저장한다 (시간대별 세그먼트는 추후 확장).
@Model
final class StudySession {
    var startedAt: Date
    var endedAt: Date?
    var productiveSeconds: TimeInterval
    var distractionSeconds: TimeInterval
    var neutralSeconds: TimeInterval
    var idleSeconds: TimeInterval

    init(startedAt: Date = .now) {
        self.startedAt = startedAt
        self.endedAt = nil
        self.productiveSeconds = 0
        self.distractionSeconds = 0
        self.neutralSeconds = 0
        self.idleSeconds = 0
    }

    /// 관측 구간 dt를 해당 카테고리에 누적. 유휴면 카테고리와 무관하게 유휴로 계산.
    func accumulate(dt: TimeInterval, category: ActivityCategory, isIdle: Bool) {
        guard dt > 0 else { return }
        if isIdle {
            idleSeconds += dt
            return
        }
        switch category {
        case .productive: productiveSeconds += dt
        case .distraction: distractionSeconds += dt
        case .neutral: neutralSeconds += dt
        }
    }

    /// 집중율: 유휴를 제외한 활동 시간 중 생산 비율. 활동이 없으면 0.
    var focusRate: Double {
        let active = productiveSeconds + distractionSeconds + neutralSeconds
        guard active > 0 else { return 0 }
        return productiveSeconds / active
    }

    /// 총 세션 시간 (진행 중이면 현재까지)
    var totalSeconds: TimeInterval {
        (endedAt ?? .now).timeIntervalSince(startedAt)
    }
}
