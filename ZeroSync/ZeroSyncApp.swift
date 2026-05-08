import SwiftUI
import SwiftData

@main
struct ZeroSyncApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var sharedModelContainer: ModelContainer = {
        let schema = Schema([Message.self])
        let config = ModelConfiguration(schema: schema, isStoredInMemoryOnly: false)
        do {
            return try ModelContainer(for: schema, configurations: [config])
        } catch {
            fatalError("ModelContainer 생성 실패: \(error)")
        }
    }()

    var body: some Scene {
        // 메인 홈 창 (Dock 앱)
        WindowGroup {
            HomeView()
        }
        .modelContainer(sharedModelContainer)
        .defaultSize(width: 900, height: 640)

        // 메뉴바 팝업
        MenuBarExtra("ZeroSync", systemImage: "brain.head.profile") {
            MenuBarView()
        }
        .menuBarExtraStyle(.window)
        .modelContainer(sharedModelContainer)

        // 설정 창
        Window("설정", id: "settings") {
            MainView()
        }
        .windowResizability(.contentSize)
        .defaultPosition(.center)
    }
}
