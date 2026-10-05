import Foundation

/// 활동 분류 결과
enum ActivityCategory: String, Codable, Sendable {
    case productive   // 생산 (코딩·노트 작성)
    case distraction  // 딴짓 (유튜브 등)
    case neutral      // 중립
}

/// 분류 규칙 — 추후 설정 화면에서 사용자 편집, UserDefaults에 JSON 저장
struct ActivityRules: Codable, Sendable {
    var productiveApps: Set<String>
    var distractionTitleKeywords: [String]

    static let `default` = ActivityRules(
        productiveApps: ["Xcode", "Terminal", "iTerm2", "Visual Studio Code", "Obsidian", "Cursor"],
        distractionTitleKeywords: ["YouTube", "youtube.com", "Netflix", "Twitch", "인스타그램", "Instagram"]
    )
}

/// 앱 이름 + 창 제목 → 카테고리. 순수 함수라 단위 테스트 대상.
struct ActivityClassifier: Sendable {
    var rules: ActivityRules

    func classify(appName: String, windowTitle: String?) -> ActivityCategory {
        // 딴짓 키워드가 최우선 — 브라우저가 생산 앱 목록에 있어도 유튜브면 딴짓
        if let title = windowTitle,
           rules.distractionTitleKeywords.contains(where: { title.localizedCaseInsensitiveContains($0) }) {
            return .distraction
        }
        if rules.productiveApps.contains(appName) {
            return .productive
        }
        return .neutral
    }
}
