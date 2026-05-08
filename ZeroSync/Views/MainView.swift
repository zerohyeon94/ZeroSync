import SwiftUI
import SwiftData

struct MainView: View {
    // API
    @AppStorage("apiKey") private var apiKey = ""
    @State private var isEditingKey = false

    // 사용자 정보
    @AppStorage("userName") private var userName = ""
    @AppStorage("userOccupation") private var userOccupation = ""
    @AppStorage("userMemo") private var userMemo = ""

    // 앱 설정
    @AppStorage("defaultPersona") private var defaultPersonaRaw = Persona.alpha.rawValue
    @AppStorage("keepHistory") private var keepHistory = true

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

    var body: some View {
        Form {
            apiSection
            userSection
            appSection
            historySection
            infoSection
        }
        .formStyle(.grouped)
        .frame(width: 460, height: 520)
        .navigationTitle("설정")
        .confirmationDialog("대화 기록을 모두 삭제할까요?", isPresented: $showClearConfirm, titleVisibility: .visible) {
            Button("삭제", role: .destructive) { clearHistory() }
            Button("취소", role: .cancel) {}
        } message: {
            Text("삭제한 기록은 복구할 수 없습니다.")
        }
    }

    // MARK: - Sections

    private var apiSection: some View {
        Section {
            if isEditingKey {
                SecureField("sk-ant-...", text: $apiKey)
                    .onSubmit { isEditingKey = false }
            } else {
                HStack {
                    Text(apiKey.isEmpty ? "미설정" : maskedKey)
                        .foregroundStyle(apiKey.isEmpty ? .red : .secondary)
                        .font(.system(.body, design: .monospaced))
                    Spacer()
                    Button(apiKey.isEmpty ? "입력" : "변경") {
                        isEditingKey = true
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(Color.accentColor)
                }
            }
        } header: {
            Text("Claude API 키")
        } footer: {
            Text("api.anthropic.com → API Keys에서 발급. 로컬에만 저장됩니다.")
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
                    .background(Color(nsColor: .textBackgroundColor))
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
            Picker("기본 페르소나", selection: defaultPersona) {
                ForEach(Persona.allCases) { persona in
                    Text(persona.displayName).tag(persona)
                }
            }
            Toggle("대화 기록 유지", isOn: $keepHistory)
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
            LabeledContent("AI 모델", value: ClaudeService.model)
            LabeledContent("버전", value: "0.1.0")
        }
    }

    // MARK: - Helpers

    private var maskedKey: String {
        guard apiKey.count > 8 else { return String(repeating: "•", count: apiKey.count) }
        let prefix = String(apiKey.prefix(7))
        let suffix = String(apiKey.suffix(4))
        return prefix + "..." + suffix
    }

    private func clearHistory() {
        for message in messages {
            modelContext.delete(message)
        }
    }
}
