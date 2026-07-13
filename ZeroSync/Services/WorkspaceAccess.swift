import AppKit
import Foundation

/// 대화에 활용할 로컬 지식 폴더 종류
enum KnowledgeFolder: String, CaseIterable, Identifiable {
    case vault
    case developer

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .vault: return "Obsidian Vault"
        case .developer: return "Developer 폴더"
        }
    }

    var bookmarkKey: String { "knowledgeBookmark_\(rawValue)" }

    /// NSOpenPanel 초기 위치 힌트
    var suggestedPath: String {
        let home = NSHomeDirectory()
        switch self {
        case .vault:
            return home + "/Library/Mobile Documents/iCloud~md~obsidian/Documents"
        case .developer:
            return home + "/Developer"
        }
    }
}

/// 샌드박스 환경에서 보안 범위 북마크로 폴더 접근을 관리한다.
/// 사용 패턴:
///   guard let url = WorkspaceAccess.resolveURL(for: .vault) else { ... }
///   let ok = url.startAccessingSecurityScopedResource()
///   defer { if ok { url.stopAccessingSecurityScopedResource() } }
nonisolated enum WorkspaceAccess {

    /// 폴더 선택 패널을 띄우고 보안 범위 북마크를 저장한다.
    @MainActor
    static func pickFolder(_ folder: KnowledgeFolder) {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.prompt = "선택"
        panel.message = "\(folder.displayName)를 선택해주세요."
        panel.directoryURL = URL(fileURLWithPath: folder.suggestedPath)

        guard panel.runModal() == .OK, let url = panel.url else { return }
        saveBookmark(url: url, for: folder)
    }

    static func saveBookmark(url: URL, for folder: KnowledgeFolder) {
        guard let data = try? url.bookmarkData(
            options: .withSecurityScope,
            includingResourceValuesForKeys: nil,
            relativeTo: nil
        ) else { return }
        UserDefaults.standard.set(data, forKey: folder.bookmarkKey)
    }

    /// 저장된 북마크를 URL로 복원한다. 만료 시 자동 갱신을 시도한다.
    static func resolveURL(for folder: KnowledgeFolder) -> URL? {
        guard let data = UserDefaults.standard.data(forKey: folder.bookmarkKey) else {
            return nil
        }

        var isStale = false
        guard let url = try? URL(
            resolvingBookmarkData: data,
            options: .withSecurityScope,
            relativeTo: nil,
            bookmarkDataIsStale: &isStale
        ) else {
            return nil
        }

        if isStale {
            saveBookmark(url: url, for: folder)
        }
        return url
    }

    static func isConnected(_ folder: KnowledgeFolder) -> Bool {
        resolveURL(for: folder) != nil
    }

    static func displayPath(for folder: KnowledgeFolder) -> String? {
        guard let url = resolveURL(for: folder) else { return nil }
        return url.path.replacingOccurrences(of: NSHomeDirectory(), with: "~")
    }

    static func disconnect(_ folder: KnowledgeFolder) {
        UserDefaults.standard.removeObject(forKey: folder.bookmarkKey)
    }
}
