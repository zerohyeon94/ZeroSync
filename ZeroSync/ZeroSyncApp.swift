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
        MenuBarExtra("ZeroSync", systemImage: "brain.head.profile") {
            MenuBarView()
        }
        .menuBarExtraStyle(.window)
        .modelContainer(sharedModelContainer)

        Window("설정", id: "settings") {
            MainView()
        }
        .windowResizability(.contentSize)
        .defaultPosition(.center)
    }
}
