import SwiftUI
import SwiftData

@Observable
final class ChatViewModel {
    var inputText = ""
    var isLoading = false
    var errorMessage: String?

    func send(currentMessages: [Message], context: ModelContext) async {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isLoading else { return }

        inputText = ""
        isLoading = true
        errorMessage = nil

        let history = currentMessages.map {
            (role: $0.isUser ? "user" : "assistant", content: $0.content)
        }
        let fullHistory = history + [(role: "user", content: text)]

        let userMsg = Message(content: text, isUser: true)
        context.insert(userMsg)

        // 로컬 문서 검색은 파일 IO가 많아 백그라운드에서 수행
        let knowledge = await Task.detached(priority: .userInitiated) {
            KnowledgeService.buildContext(for: text)
        }.value

        let service = OllamaService()
        do {
            async let alphaTask = service.send(history: fullHistory, persona: .alpha, knowledge: knowledge)
            async let betaTask  = service.send(history: fullHistory, persona: .beta, knowledge: knowledge)
            let (alphaReply, betaReply) = try await (alphaTask, betaTask)
            context.insert(Message(content: alphaReply, isUser: false, persona: .alpha))
            context.insert(Message(content: betaReply,  isUser: false, persona: .beta))
        } catch {
            errorMessage = error.localizedDescription
            context.delete(userMsg)
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
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(messages) { message in
                            MessageBubble(message: message)
                                .id(message.id)
                        }
                        if viewModel.isLoading {
                            HStack(spacing: 8) {
                                ProgressView().scaleEffect(0.7)
                                Text("Alpha · Beta 응답 중...")
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
                    withAnimation { proxy.scrollTo("loading", anchor: .bottom) }
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
                        .foregroundStyle(
                            viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                ? Color.secondary : Color.accentColor
                        )
                }
                .buttonStyle(.plain)
                .disabled(
                    viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    || viewModel.isLoading
                )
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
        }
    }
}
