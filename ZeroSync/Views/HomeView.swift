import SwiftUI
import SwiftData

struct HomeView: View {
    @Environment(\.modelContext) private var modelContext
    @Query(sort: \Message.timestamp) private var messages: [Message]

    @State private var viewModel = ChatViewModel()
    @Environment(\.openWindow) private var openWindow

    private var accentCol: Color {
        viewModel.selectedPersona == .alpha
            ? Color(red: 0, green: 0.4, blue: 1)
            : Color(red: 1.0, green: 0.42, blue: 0.208)
    }

    var body: some View {
        ZStack {
            Color(red: 0.012, green: 0.024, blue: 0.031).ignoresSafeArea()

            VStack(spacing: 0) {
                topBar
                orbArea
                errorRow
                inputBar
            }
        }
        .preferredColorScheme(.dark)
    }

    // MARK: - Subviews

    private var topBar: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 2) {
                Text("ZERO-ALPHA-BETA")
                    .font(.system(size: 11, weight: .semibold, design: .monospaced))
                    .foregroundStyle(Color(red: 0, green: 0.96, blue: 1).opacity(0.7))
                    .tracking(3)
                Text("AI ASSISTANT SYSTEM")
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundStyle(.quaternary)
                    .tracking(2)
            }
            Spacer()
            PersonaSelector(selected: $viewModel.selectedPersona)
            Button {
                openWindow(id: "settings")
                NSApp.activate(ignoringOtherApps: true)
            } label: {
                Image(systemName: "gearshape")
                    .font(.system(size: 14, weight: .regular))
                    .foregroundStyle(Color.white.opacity(0.4))
                    .frame(width: 28, height: 28)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help("설정")
        }
        .padding(.horizontal, 24)
        .padding(.top, 14)
        .padding(.bottom, 10)
    }

    private var orbArea: some View {
        ZStack(alignment: .bottom) {
            OrbView(
                state: viewModel.isLoading ? .thinking : .idle,
                persona: viewModel.selectedPersona
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            if !messages.isEmpty || viewModel.isLoading {
                ConversationOverlay(
                    messages: Array(messages.suffix(3)),
                    isLoading: viewModel.isLoading
                )
                .padding(.horizontal, 28)
                .padding(.bottom, 20)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    @ViewBuilder
    private var errorRow: some View {
        if let error = viewModel.errorMessage {
            Text(error)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(.red.opacity(0.8))
                .padding(.horizontal, 24)
                .padding(.bottom, 6)
        }
    }

    private var inputBar: some View {
        HStack(spacing: 12) {
            TextField("제로에게 말하기...", text: $viewModel.inputText, axis: .vertical)
                .textFieldStyle(.plain)
                .lineLimit(1...3)
                .font(.system(size: 13))
                .foregroundStyle(.white)
                .tint(Color(red: 0, green: 0.96, blue: 1))
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(inputBackground)
                .onSubmit {
                    Task { await viewModel.send(currentMessages: messages, context: modelContext) }
                }

            Button {
                Task { await viewModel.send(currentMessages: messages, context: modelContext) }
            } label: {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 28))
                    .foregroundStyle(
                        viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                            ? Color.white.opacity(0.15)
                            : accentCol
                    )
            }
            .buttonStyle(.plain)
            .disabled(viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isLoading)
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 14)
        .background(
            Rectangle()
                .fill(Color.white.opacity(0.03))
                .overlay(alignment: .top) {
                    Rectangle().fill(Color.white.opacity(0.07)).frame(height: 0.5)
                }
        )
    }

    private var inputBackground: some View {
        RoundedRectangle(cornerRadius: 10, style: .continuous)
            .fill(Color.white.opacity(0.05))
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .strokeBorder(accentCol.opacity(0.35), lineWidth: 1)
            )
    }
}

// MARK: - Conversation Overlay

private struct ConversationOverlay: View {
    let messages: [Message]
    let isLoading: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(messages.enumerated()), id: \.element.id) { idx, msg in
                HoloBubble(message: msg)
                    .opacity(fadeOpacity(index: idx, total: messages.count))
            }
            if isLoading {
                HoloTypingIndicator()
            }
        }
        .frame(maxWidth: 560)
    }

    private func fadeOpacity(index: Int, total: Int) -> Double {
        guard total > 1 else { return 1.0 }
        let distFromEnd = total - 1 - index
        switch distFromEnd {
        case 0: return 1.0
        case 1: return 0.55
        default: return 0.22
        }
    }
}

// MARK: - Holo Bubble

private struct HoloBubble: View {
    let message: Message

    private var isUser: Bool { message.isUser }

    private var accentColor: Color {
        isUser
            ? Color(red: 1.0, green: 0.42, blue: 0.208)
            : Color(red: 0, green: 0.96, blue: 1)
    }

    private var fillColor: Color {
        isUser
            ? Color(red: 1.0, green: 0.42, blue: 0.208).opacity(0.08)
            : Color(red: 0, green: 0.4, blue: 1).opacity(0.08)
    }

    private var label: String {
        isUser ? "ZERO" : (message.persona?.displayName.uppercased() ?? "AI")
    }

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            if isUser { Spacer(minLength: 48) }

            VStack(alignment: isUser ? .trailing : .leading, spacing: 4) {
                Text(label)
                    .font(.system(size: 8, design: .monospaced))
                    .fontWeight(.semibold)
                    .foregroundStyle(accentColor.opacity(0.65))
                    .tracking(2)

                Text(message.content)
                    .font(.system(size: 12.5))
                    .foregroundStyle(Color.white.opacity(0.88))
                    .lineLimit(5)
                    .multilineTextAlignment(isUser ? .trailing : .leading)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 9)
                    .background(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .fill(fillColor)
                            .overlay(
                                RoundedRectangle(cornerRadius: 12, style: .continuous)
                                    .strokeBorder(accentColor.opacity(0.28), lineWidth: 1)
                            )
                    )
                    .background(
                        .ultraThinMaterial.opacity(0.4),
                        in: RoundedRectangle(cornerRadius: 12, style: .continuous)
                    )
            }

            if !isUser { Spacer(minLength: 48) }
        }
    }
}

// MARK: - Typing Indicator

private struct HoloTypingIndicator: View {
    @State private var phase = false

    var body: some View {
        HStack(spacing: 10) {
            HStack(spacing: 5) {
                ForEach(0..<3, id: \.self) { i in
                    Circle()
                        .fill(Color(red: 0, green: 0.96, blue: 1))
                        .frame(width: 5, height: 5)
                        .scaleEffect(phase ? 1.3 : 0.7)
                        .opacity(phase ? 1.0 : 0.3)
                        .animation(
                            .easeInOut(duration: 0.55)
                            .repeatForever(autoreverses: true)
                            .delay(Double(i) * 0.18),
                            value: phase
                        )
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(Color(red: 0, green: 0.4, blue: 1).opacity(0.08))
                    .overlay(
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .strokeBorder(Color(red: 0, green: 0.96, blue: 1).opacity(0.28), lineWidth: 1)
                    )
            )

            Text("PROCESSING")
                .font(.system(size: 8, design: .monospaced))
                .foregroundStyle(Color(red: 0, green: 0.96, blue: 1).opacity(0.45))
                .tracking(2)

            Spacer()
        }
        .onAppear { phase = true }
    }
}
