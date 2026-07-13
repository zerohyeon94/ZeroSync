import SwiftUI
import SwiftData

struct MainView: View {
    // Ollama
    @AppStorage("ollamaModel") private var ollamaModel = OllamaService.defaultModel
    @State private var installedModels: [String] = []
    @State private var ollamaStatus: OllamaStatus = .checking

    // 로컬 지식 폴더 (북마크 변경 시 뷰 갱신 트리거)
    @State private var folderRefresh = 0

    enum OllamaStatus {
        case checking, running, notRunning

        var label: String {
            switch self {
            case .checking: return "확인 중..."
            case .running: return "실행 중"
            case .notRunning: return "미실행"
            }
        }
    }

    // 사용자 정보
    @AppStorage("userName") private var userName = ""
    @AppStorage("userOccupation") private var userOccupation = ""
    @AppStorage("userMemo") private var userMemo = ""

    // 앱 설정
    @AppStorage("defaultPersona") private var defaultPersonaRaw = Persona.alpha.rawValue
    @AppStorage("keepHistory") private var keepHistory = true
    @AppStorage("appTheme") private var appThemeRaw = AppTheme.light.rawValue
    @AppStorage(DesktopPetManager.enabledKey) private var desktopPetsEnabled = true

    // 히스토리 초기화
    @Environment(\.modelContext) private var modelContext
    @Query private var messages: [Message]
    @State private var showClearConfirm = false

    private var defaultPersona: Binding<Persona> {
        Binding(
            get: { Persona(rawValue: defaultPersonaRaw) ?? .alpha },
            set: { defaultPersonaRaw = $0.rawValue }
        )
    }

    private var appTheme: Binding<AppTheme> {
        Binding(
            get: { AppTheme(rawValue: appThemeRaw) ?? .light },
            set: { appThemeRaw = $0.rawValue }
        )
    }

    private var currentTheme: AppTheme {
        AppTheme(rawValue: appThemeRaw) ?? .light
    }

    var body: some View {
        Form {
            ollamaSection
            knowledgeSection
            userSection
            appSection
            historySection
            infoSection
        }
        .formStyle(.grouped)
        .frame(width: 460, height: 560)
        .navigationTitle("설정")
        .task { await refreshOllamaStatus() }
        .animation(.easeInOut(duration: 0.25), value: appThemeRaw)
        .confirmationDialog("대화 기록을 모두 삭제할까요?", isPresented: $showClearConfirm, titleVisibility: .visible) {
            Button("삭제", role: .destructive) { clearHistory() }
            Button("취소", role: .cancel) {}
        } message: {
            Text("삭제한 기록은 복구할 수 없습니다.")
        }
    }

    // MARK: - Sections

    private var ollamaSection: some View {
        Section {
            HStack {
                Text("서버 상태")
                Spacer()
                Text(ollamaStatus.label)
                    .foregroundStyle(ollamaStatus == .running ? .green : (ollamaStatus == .notRunning ? .red : .secondary))
                Button {
                    Task { await refreshOllamaStatus() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .foregroundStyle(Color.accentColor)
                .help("상태 새로고침")
            }

            if installedModels.isEmpty {
                LabeledContent("모델") {
                    TextField(OllamaService.defaultModel, text: $ollamaModel)
                        .multilineTextAlignment(.trailing)
                }
            } else {
                Picker("모델", selection: $ollamaModel) {
                    ForEach(installedModels, id: \.self) { model in
                        Text(model).tag(model)
                    }
                    if !installedModels.contains(ollamaModel) {
                        Text(ollamaModel).tag(ollamaModel)
                    }
                }
            }
        } header: {
            Text("Ollama (로컬 AI)")
        } footer: {
            Text("ollama.com에서 설치 후 'ollama pull \(OllamaService.defaultModel)'로 모델을 받아주세요. 모든 대화는 이 Mac 안에서만 처리됩니다.")
        }
    }

    private var knowledgeSection: some View {
        Section {
            ForEach(KnowledgeFolder.allCases) { folder in
                folderRow(folder)
            }
        } header: {
            Text("로컬 지식 연동")
        } footer: {
            Text("연결한 폴더의 md 문서를 알파·베타가 대화에 참고합니다. 읽기 전용으로만 접근합니다.")
        }
        .id(folderRefresh)
    }

    private func folderRow(_ folder: KnowledgeFolder) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(folder.displayName)
                Text(WorkspaceAccess.displayPath(for: folder) ?? "미연결")
                    .font(.caption)
                    .foregroundStyle(WorkspaceAccess.isConnected(folder) ? Color.secondary : Color.red)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            Spacer()
            if WorkspaceAccess.isConnected(folder) {
                Button("해제") {
                    WorkspaceAccess.disconnect(folder)
                    folderRefresh += 1
                }
                .buttonStyle(.plain)
                .foregroundStyle(.red)
            }
            Button(WorkspaceAccess.isConnected(folder) ? "변경" : "연결") {
                WorkspaceAccess.pickFolder(folder)
                folderRefresh += 1
            }
            .buttonStyle(.plain)
            .foregroundStyle(Color.accentColor)
        }
    }

    private var userSection: some View {
        Section {
            LabeledContent("이름 / 호칭") {
                TextField("제로", text: $userName)
                    .multilineTextAlignment(.trailing)
            }
            LabeledContent("직업 / 역할") {
                TextField("예: iOS 개발자, 디자이너...", text: $userOccupation)
                    .multilineTextAlignment(.trailing)
            }
            VStack(alignment: .leading, spacing: 6) {
                Text("알파·베타에게 알릴 추가 정보")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                TextEditor(text: $userMemo)
                    .font(.system(size: 12))
                    .frame(minHeight: 60, maxHeight: 80)
                    .scrollContentBackground(.hidden)
                    .background(textEditorBackground)
                    .clipShape(RoundedRectangle(cornerRadius: 6))
            }
            .padding(.vertical, 4)
        } header: {
            Text("사용자 정보")
        } footer: {
            Text("입력한 정보는 알파·베타가 대화 맥락을 이해하는 데 활용됩니다.")
        }
    }

    private var appSection: some View {
        Section("앱 설정") {
            Picker("화면 모드", selection: appTheme) {
                ForEach(AppTheme.allCases) { theme in
                    Text(theme.displayName).tag(theme)
                }
            }
            .pickerStyle(.segmented)

            Picker("기본 페르소나", selection: defaultPersona) {
                ForEach(Persona.allCases) { persona in
                    Text(persona.displayName).tag(persona)
                }
            }
            Toggle("대화 기록 유지", isOn: $keepHistory)
            Toggle("데스크톱 캐릭터 (알파·베타)", isOn: $desktopPetsEnabled)
                .onChange(of: desktopPetsEnabled) {
                    DesktopPetManager.shared.applyEnabledSetting()
                }
        }
    }

    private var historySection: some View {
        Section {
            HStack {
                Text("저장된 메시지")
                Spacer()
                Text("\(messages.count)개")
                    .foregroundStyle(.secondary)
            }
            Button("대화 기록 전체 삭제", role: .destructive) {
                showClearConfirm = true
            }
            .disabled(messages.isEmpty)
        } header: {
            Text("대화 기록")
        }
    }

    private var infoSection: some View {
        Section("정보") {
            LabeledContent("AI 모델", value: ollamaModel)
            LabeledContent("버전", value: "0.1.0")
        }
    }

    // MARK: - Helpers

    private func refreshOllamaStatus() async {
        ollamaStatus = .checking
        do {
            installedModels = try await OllamaService.listModels()
            ollamaStatus = .running
        } catch {
            installedModels = []
            ollamaStatus = .notRunning
        }
    }

    private var textEditorBackground: Color {
        currentTheme == .dark
            ? Color(nsColor: .controlBackgroundColor).opacity(0.72)
            : Color(nsColor: .textBackgroundColor)
    }

    private func clearHistory() {
        for message in messages {
            modelContext.delete(message)
        }
    }
}
