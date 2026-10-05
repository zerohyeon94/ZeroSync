import Testing
@testable import ZeroSync

struct ActivityClassifierTests {
    let classifier = ActivityClassifier(rules: .default)

    @Test func 코딩_앱은_생산으로_분류() {
        #expect(classifier.classify(appName: "Xcode", windowTitle: "ContentView.swift") == .productive)
        #expect(classifier.classify(appName: "Terminal", windowTitle: nil) == .productive)
    }

    @Test func 창_제목에_유튜브가_있으면_딴짓() {
        #expect(classifier.classify(appName: "Google Chrome", windowTitle: "뮤직비디오 - YouTube") == .distraction)
        #expect(classifier.classify(appName: "Safari", windowTitle: "youtube.com") == .distraction)
    }

    @Test func 모르는_앱은_중립() {
        #expect(classifier.classify(appName: "Finder", windowTitle: nil) == .neutral)
    }

    @Test func 창_제목이_없는_브라우저는_중립() {
        // 손쉬운 사용 권한 거부 시 축소 모드: 브라우저를 딴짓으로 단정하지 않는다
        #expect(classifier.classify(appName: "Google Chrome", windowTitle: nil) == .neutral)
    }

    @Test func 딴짓_키워드가_생산_앱보다_우선() {
        // 생산 앱 목록에 브라우저를 넣어도 유튜브 제목이면 딴짓
        var rules = ActivityRules.default
        rules.productiveApps.insert("Google Chrome")
        let c = ActivityClassifier(rules: rules)
        #expect(c.classify(appName: "Google Chrome", windowTitle: "강의 - YouTube") == .distraction)
    }
}
