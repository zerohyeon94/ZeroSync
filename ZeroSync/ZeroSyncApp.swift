import SwiftUI
import SwiftData

enum AppTheme: String, CaseIterable, Identifiable {
    case light
    case dark

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .light: return "라이트"
        case .dark: return "다크"
        }
    }

    var colorScheme: ColorScheme {
        switch self {
        case .light: return .light
        case .dark: return .dark
        }
    }
}

@main
struct ZeroSyncApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @AppStorage("appTheme") private var appThemeRaw = AppTheme.light.rawValue

    private var appTheme: AppTheme {
        AppTheme(rawValue: appThemeRaw) ?? .light
    }

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
                .preferredColorScheme(appTheme.colorScheme)
        }
        .modelContainer(sharedModelContainer)
        .defaultSize(width: 900, height: 640)

        // 메뉴바 팝업
        MenuBarExtra("ZeroSync", systemImage: "brain.head.profile") {
            MenuBarView()
                .preferredColorScheme(appTheme.colorScheme)
        }
        .menuBarExtraStyle(.window)
        .modelContainer(sharedModelContainer)

        // 설정 창
        Window("설정", id: "settings") {
            MainView()
                .preferredColorScheme(appTheme.colorScheme)
        }
        .modelContainer(sharedModelContainer)
        .windowResizability(.contentSize)
        .defaultPosition(.center)
    }
}
