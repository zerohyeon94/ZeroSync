import SwiftUI

struct MainView: View {
    @AppStorage("apiKey") private var apiKey = ""
    @State private var maskedKey = ""
    @State private var isEditing = false

    var body: some View {
        Form {
            Section("Claude API") {
                if isEditing {
                    SecureField("API 키 입력", text: $apiKey)
                        .onSubmit { isEditing = false }
                } else {
                    HStack {
                        Text(apiKey.isEmpty ? "미설정" : String(repeating: "•", count: min(apiKey.count, 20)))
                            .foregroundStyle(apiKey.isEmpty ? .red : .secondary)
                        Spacer()
                        Button(apiKey.isEmpty ? "입력" : "변경") {
                            isEditing = true
                        }
                        .buttonStyle(.plain)
                        .foregroundStyle(Color.accentColor)
                    }
                }
                Text("api.anthropic.com에서 발급받은 키를 입력하세요.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("모델") {
                LabeledContent("AI 모델", value: ClaudeService.model)
            }

            Section("정보") {
                LabeledContent("버전", value: "0.1.0")
                LabeledContent("제작", value: "Zero-Alpha-Beta")
            }
        }
        .formStyle(.grouped)
        .frame(width: 420, height: 300)
        .navigationTitle("설정")
    }
}
