//
//  ZeroSyncApp.swift
//  ZeroSync
//
//  Created by 조영현 on 4/29/26.
//

import SwiftUI
import SwiftData

@main
struct ZeroSyncApp: App {
    
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    
    var sharedModelContainer: ModelContainer = {
        let schema = Schema([
            Item.self,
        ])
        let modelConfiguration = ModelConfiguration(schema: schema, isStoredInMemoryOnly: false)
        
        do {
            return try ModelContainer(for: schema, configurations: [modelConfiguration])
        } catch {
            fatalError("Could not create ModelContainer: \(error)")
        }
    }()
    
    var body: some Scene {
        // 메인 윈도우 (Dock에 표시됨)
        WindowGroup {
            MainView()
        }
        .windowStyle(.hiddenTitleBar)
        
        // 메뉴바 아이콘
        MenuBarExtra("ZeroSync", systemImage: "clock.arrow.2.circlepath") {
            MenuBarView()
        }
    }
}
