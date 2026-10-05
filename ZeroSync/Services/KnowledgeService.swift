import Foundation

/// 사용자 질문에서 키워드를 뽑아 Obsidian vault와 Developer 폴더의 문서를 검색하고,
/// 관련 스니펫을 시스템 프롬프트에 주입할 참고 자료 블록으로 만든다.
/// 파일 IO가 많으므로 메인 액터 밖(Task.detached)에서 호출한다.
nonisolated enum KnowledgeService {

    private static let maxCandidateFiles = 2000
    private static let maxContentScanFiles = 200
    private static let maxFileReadBytes = 64 * 1024
    private static let maxSnippets = 4
    private static let snippetLength = 1200
    private static let maxTotalChars = 6000

    private static let excludedDirectories: Set<String> = [
        ".obsidian", ".trash", ".git", "Templates", "Assets", "node_modules"
    ]

    /// Developer 프로젝트에서 읽을 문서 파일명
    private static let projectDocNames: Set<String> = [
        "readme.md", "claude.md", "agents.md", "concept.md"
    ]

    // MARK: - Public

    static func buildContext(for query: String) -> String? {
        let vaultURL = WorkspaceAccess.resolveURL(for: .vault)
        let developerURL = WorkspaceAccess.resolveURL(for: .developer)
        guard vaultURL != nil || developerURL != nil else { return nil }

        var files: [IndexedFile] = []
        var overviewLines: [String] = []

        if let vaultURL {
            let started = vaultURL.startAccessingSecurityScopedResource()
            defer { if started { vaultURL.stopAccessingSecurityScopedResource() } }
            files += collectVaultFiles(root: vaultURL)
            overviewLines.append("- Obsidian vault 최상위: " + topLevelNames(of: vaultURL).joined(separator: ", "))
        }

        if let developerURL {
            let started = developerURL.startAccessingSecurityScopedResource()
            defer { if started { developerURL.stopAccessingSecurityScopedResource() } }
            files += collectProjectDocs(root: developerURL)
            overviewLines.append("- Developer 프로젝트: " + topLevelNames(of: developerURL).joined(separator: ", "))
        }

        let keywords = extractKeywords(from: query)
        let snippets = search(keywords: keywords, in: files)

        var blocks: [String] = []
        blocks.append("[참고 자료 — 사용자의 로컬 문서·프로젝트에서 자동 검색됨]")
        blocks.append("## 작업 공간 개요\n" + overviewLines.joined(separator: "\n"))

        var total = blocks.joined().count
        for snippet in snippets {
            let block = "## 파일: \(snippet.relativePath)\n\(snippet.text)"
            guard total + block.count <= maxTotalChars else { break }
            blocks.append(block)
            total += block.count
        }

        blocks.append("위 자료가 질문과 관련 있으면 활용하고, 관련 없으면 무시하세요. 자료에 없는 내용을 아는 것처럼 지어내지 마세요.")
        return blocks.joined(separator: "\n\n")
    }

    // MARK: - File Collection

    private struct IndexedFile {
        let url: URL
        let relativePath: String
        let modified: Date
    }

    private struct Snippet {
        let relativePath: String
        let text: String
    }

    private static func collectVaultFiles(root: URL) -> [IndexedFile] {
        collectMarkdown(root: root, rootLabel: "vault") { url in
            url.pathExtension.lowercased() == "md"
        }
    }

    /// Developer 폴더: 프로젝트 최상위 문서 + 각 프로젝트 docs/ 하위 md만 수집
    private static func collectProjectDocs(root: URL) -> [IndexedFile] {
        collectMarkdown(root: root, rootLabel: "developer") { url in
            guard url.pathExtension.lowercased() == "md" else { return false }
            let name = url.lastPathComponent.lowercased()
            let path = url.path.lowercased()
            return projectDocNames.contains(name) || path.contains("/docs/")
        }
    }

    private static func collectMarkdown(
        root: URL,
        rootLabel: String,
        include: (URL) -> Bool
    ) -> [IndexedFile] {
        let keys: [URLResourceKey] = [.isDirectoryKey, .contentModificationDateKey, .nameKey]
        guard let enumerator = FileManager.default.enumerator(
            at: root,
            includingPropertiesForKeys: keys,
            options: [.skipsHiddenFiles, .skipsPackageDescendants]
        ) else { return [] }

        var result: [IndexedFile] = []
        let rootPath = root.path

        for case let url as URL in enumerator {
            guard result.count < maxCandidateFiles else { break }
            guard let values = try? url.resourceValues(forKeys: Set(keys)) else { continue }

            if values.isDirectory == true {
                if excludedDirectories.contains(url.lastPathComponent) {
                    enumerator.skipDescendants()
                }
                continue
            }

            guard include(url) else { continue }
            var relative = url.path
            if relative.hasPrefix(rootPath) {
                relative = String(relative.dropFirst(rootPath.count)).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            }
            result.append(IndexedFile(
                url: url,
                relativePath: "\(rootLabel)/\(relative)",
                modified: values.contentModificationDate ?? .distantPast
            ))
        }
        return result
    }

    private static func topLevelNames(of root: URL) -> [String] {
        let contents = (try? FileManager.default.contentsOfDirectory(
            at: root,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        )) ?? []
        return contents
            .map(\.lastPathComponent)
            .filter { !excludedDirectories.contains($0) }
            .sorted()
    }

    // MARK: - Keyword Extraction

    private static let stopwords: Set<String> = [
        "그리고", "그래서", "하지만", "그런데", "지금", "현재", "오늘", "내일", "어제",
        "대해", "대해서", "관련", "관련해서", "어떻게", "어떤", "무엇", "뭐야", "뭐가",
        "알려줘", "알려주세요", "해줘", "해주세요", "말해줘", "궁금해", "있어", "있는",
        "있나요", "인가요", "할까", "그거", "이거", "저거", "너네", "너희", "우리",
        "the", "and", "for", "with", "what", "how", "about"
    ]

    /// 흔한 한국어 조사 접미. 긴 것부터 매칭한다.
    private static let particleSuffixes = [
        "에서는", "에서도", "으로는", "한테서", "에게서",
        "에서", "으로", "이랑", "하고", "에게", "한테", "까지", "부터", "처럼", "보다",
        "은", "는", "이", "가", "을", "를", "에", "의", "도", "로", "와", "과", "만", "요"
    ]

    static func extractKeywords(from query: String) -> [String] {
        let separators = CharacterSet.alphanumerics
            .union(CharacterSet(charactersIn: "가"..."힣"))
            .inverted
        let tokens = query.components(separatedBy: separators)

        var keywords: [String] = []
        for raw in tokens {
            var token = raw.lowercased()
            guard token.count >= 2 else { continue }

            if !stopwords.contains(token), token.count >= 3, containsHangul(token) {
                for suffix in particleSuffixes where token.hasSuffix(suffix) && token.count - suffix.count >= 2 {
                    token = String(token.dropLast(suffix.count))
                    break
                }
            }

            guard token.count >= 2, !stopwords.contains(token), !keywords.contains(token) else { continue }
            keywords.append(token)
        }
        return Array(keywords.prefix(8))
    }

    private static func containsHangul(_ text: String) -> Bool {
        text.unicodeScalars.contains { ("가"..."힣").contains(Character($0)) }
    }

    // MARK: - Search

    private static func search(keywords: [String], in files: [IndexedFile]) -> [Snippet] {
        guard !keywords.isEmpty, !files.isEmpty else { return [] }

        // 1단계: 파일명·경로 매칭
        var nameScores: [Int: Int] = [:]
        for (index, file) in files.enumerated() {
            let path = file.relativePath.lowercased()
            let score = keywords.reduce(0) { $0 + (path.contains($1) ? 5 : 0) }
            if score > 0 { nameScores[index] = score }
        }

        // 2단계: 내용 스캔 대상 = 파일명 매칭 파일 + 최근 수정 상위 파일
        var scanIndices = Set(nameScores.keys)
        let recentIndices = files.indices
            .sorted { files[$0].modified > files[$1].modified }
            .prefix(maxContentScanFiles)
        scanIndices.formUnion(recentIndices)

        var results: [(index: Int, score: Int, content: String?, matchPosition: String.Index?)] = []
        for index in scanIndices {
            let file = files[index]
            var score = nameScores[index] ?? 0
            var content: String? = nil
            var matchPosition: String.Index? = nil

            if let text = readHead(of: file.url) {
                for keyword in keywords {
                    var searchRange = text.startIndex..<text.endIndex
                    var count = 0
                    while count < 10,
                          let found = text.range(of: keyword, options: .caseInsensitive, range: searchRange) {
                        count += 1
                        if matchPosition == nil { matchPosition = found.lowerBound }
                        searchRange = found.upperBound..<text.endIndex
                    }
                    score += count
                }
                content = text
            }

            if score > 0 {
                results.append((index, score, content, matchPosition))
            }
        }

        return results
            .sorted { $0.score > $1.score }
            .prefix(maxSnippets)
            .compactMap { result in
                guard let content = result.content else { return nil }
                return Snippet(
                    relativePath: files[result.index].relativePath,
                    text: extractSnippet(from: content, around: result.matchPosition)
                )
            }
    }

    private static func readHead(of url: URL) -> String? {
        guard let handle = try? FileHandle(forReadingFrom: url) else { return nil }
        defer { try? handle.close() }
        guard let data = try? handle.read(upToCount: maxFileReadBytes) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    /// position은 content 기준 인덱스여야 한다.
    private static func extractSnippet(from content: String, around position: String.Index?) -> String {
        guard content.count > snippetLength else {
            return content.trimmingCharacters(in: .whitespacesAndNewlines)
        }

        guard let position, position < content.endIndex else {
            return String(content.prefix(snippetLength)).trimmingCharacters(in: .whitespacesAndNewlines)
        }

        let half = snippetLength / 2
        let start = content.index(position, offsetBy: -half, limitedBy: content.startIndex) ?? content.startIndex
        let end = content.index(start, offsetBy: snippetLength, limitedBy: content.endIndex) ?? content.endIndex
        var snippet = String(content[start..<end]).trimmingCharacters(in: .whitespacesAndNewlines)
        if start > content.startIndex { snippet = "..." + snippet }
        if end < content.endIndex { snippet += "..." }
        return snippet
    }
}
