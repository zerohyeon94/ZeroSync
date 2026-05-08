import SwiftUI
import SwiftData

@Observable
final class ChatViewModel {
    var inputText = ""
    var isLoading = false
    var errorMessage: String?
    var selectedPersona: Persona = .alpha

    @ObservationIgnored
    @AppStorage("apiKey") private var apiKey = ""

    func send(currentMessages: [Message], context: ModelContext) async {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isLoading else { return }

        inputText = ""
        isLoading = true
        errorMessage = nil

        let history = currentMessages.map { (role: $0.isUser ? "user" : "assistant", content: $0.content) }
        let fullHistory = history + [(role: "user", content: text)]

        let userMessage = Message(content: text, isUser: true)
        context.insert(userMessage)

        do {
            let service = ClaudeService(apiKey: apiKey)
            let reply = try await service.send(history: fullHistory, persona: selectedPersona)
            context.insert(Message(content: reply, isUser: false, persona: selectedPersona))
        } catch {
            errorMessage = error.localizedDescription
            context.delete(userMessage)
        }

        isLoading = false
    }
}

struct ChatView: View {
    @Environment(\.modelContext) private var modelContext
    @Query(sort: \Message.timestamp) private var messages: [Message]

    @State private var viewModel = ChatViewModel()

    var body: some View {
        VStack(spacing: 0) {
            PersonaSelector(selected: $viewModel.selectedPersona)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)

            Divider()

            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(messages) { message in
                            MessageBubble(message: message)
                                .id(message.id)
                        }
                        if viewModel.isLoading {
                            HStack {
                                ProgressView()
                                    .scaleEffect(0.7)
                                Text("응답 중...")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            .padding(.horizontal, 16)
                            .id("loading")
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                }
                .onChange(of: messages.count) {
                    withAnimation {
                        if let lastId = messages.last?.id {
                            proxy.scrollTo(lastId, anchor: .bottom)
                        }
                    }
                }
                .onChange(of: viewModel.isLoading) {
                    withAnimation {
                        proxy.scrollTo("loading", anchor: .bottom)
                    }
                }
            }

            if let error = viewModel.errorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .padding(.horizontal, 12)
                    .padding(.top, 4)
            }

            Divider()

            HStack(spacing: 8) {
                TextField("메시지 입력...", text: $viewModel.inputText, axis: .vertical)
                    .textFieldStyle(.plain)
                    .lineLimit(1...4)
                    .onSubmit {
                        Task { await viewModel.send(currentMessages: messages, context: modelContext) }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                    .background(Color(nsColor: .controlBackgroundColor))
                    .clipShape(RoundedRectangle(cornerRadius: 8))

                Button {
                    Task { await viewModel.send(currentMessages: messages, context: modelContext) }
                } label: {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.title2)
                        .foregroundStyle(viewModel.inputText.isEmpty ? Color.secondary : Color.accentColor)
                }
                .buttonStyle(.plain)
                .disabled(viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isLoading)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
        }
    }
}
