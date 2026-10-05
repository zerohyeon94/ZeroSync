import SwiftUI
import SwiftData

struct HomeView: View {
    @Environment(\.modelContext) private var modelContext
    @Query(sort: \Message.timestamp) private var messages: [Message]

    @State private var viewModel = ChatViewModel()
    @Environment(\.openWindow) private var openWindow
    @AppStorage("appTheme") private var appThemeRaw = AppTheme.light.rawValue

    private let alphaBlue = Color(red: 0.294, green: 0.561, blue: 0.831)
    private let betaPink  = Color(red: 0.910, green: 0.482, blue: 0.639)
    private var appTheme: AppTheme { AppTheme(rawValue: appThemeRaw) ?? .light }
    private var isDarkTheme: Bool { appTheme == .dark }

    var body: some View {
        ZStack {
            CosmicBackgroundView(isDarkTheme: isDarkTheme)

            VStack(spacing: 0) {
                topBar
                logoArea
                errorRow
                inputBar
            }
        }
    }

    // MARK: - Subviews

    private var topBar: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 2) {
                Text("ZERO-ALPHA-BETA")
                    .font(.system(size: 11, weight: .semibold, design: .monospaced))
                    .foregroundStyle(alphaBlue)
                    .tracking(3)
                Text("AI ASSISTANT SYSTEM")
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .tracking(2)
            }
            Spacer()
            Button {
                openWindow(id: "settings")
                NSApp.activate(ignoringOtherApps: true)
            } label: {
                Image(systemName: "gearshape")
                    .font(.system(size: 14, weight: .regular))
                    .foregroundStyle(Color.primary.opacity(isDarkTheme ? 0.58 : 0.35))
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

    private var logoArea: some View {
        ZStack(alignment: .bottom) {
            ZeroLogoView(isThinking: viewModel.isLoading)
                .frame(maxWidth: .infinity, maxHeight: .infinity)

            if !messages.isEmpty || viewModel.isLoading {
                ConversationOverlay(
                    messages: Array(messages.suffix(3)),
                    isLoading: viewModel.isLoading,
                    alphaBlue: alphaBlue,
                    betaPink: betaPink
                )
                .padding(.horizontal, 28)
                .padding(.bottom, 24)
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
                .foregroundStyle(.primary)
                .tint(alphaBlue)
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
                            ? Color.primary.opacity(0.2) : alphaBlue
                    )
            }
            .buttonStyle(.plain)
            .disabled(
                viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                || viewModel.isLoading
            )
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 14)
        .background(
            Rectangle()
                .fill(.ultraThinMaterial)
                .overlay(alignment: .top) {
                    Rectangle()
                        .fill((isDarkTheme ? Color.white : Color.black).opacity(0.08))
                        .frame(height: 0.5)
                }
        )
    }

    private var inputBackground: some View {
        RoundedRectangle(cornerRadius: 10, style: .continuous)
            .fill(isDarkTheme ? Color.black.opacity(0.34) : Color.white.opacity(0.72))
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .strokeBorder(alphaBlue.opacity(isDarkTheme ? 0.58 : 0.4), lineWidth: 1)
            )
    }
}

// MARK: - Cosmic Background

private struct CosmicBackgroundView: View {
    let isDarkTheme: Bool

    var body: some View {
        ZStack {
            // 1. 베이스 그래디언트 (낮의 성운 / 밤의 심우주)
            LinearGradient(
                colors: isDarkTheme ? darkBaseColors : lightBaseColors,
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )

            // 2. 배경 이미지 — 옅게 깔아 우주 텍스처 느낌만
            Image("AppBackground")
                .resizable()
                .scaledToFill()
                .opacity(isDarkTheme ? 0.22 : 0.18)
                .blendMode(isDarkTheme ? .screen : .softLight)

            // 3. 성운 클라우드들 (시안 → 보라 → 핑크)
            nebulaCloud(
                color: isDarkTheme
                    ? Color(red: 0.20, green: 0.55, blue: 1.00)
                    : Color(red: 0.46, green: 0.74, blue: 1.00),
                center: UnitPoint(x: 0.18, y: 0.22),
                radius: 380,
                opacity: isDarkTheme ? 0.55 : 0.55
            )

            nebulaCloud(
                color: isDarkTheme
                    ? Color(red: 0.62, green: 0.30, blue: 0.92)
                    : Color(red: 0.74, green: 0.55, blue: 0.96),
                center: UnitPoint(x: 0.55, y: 0.50),
                radius: 460,
                opacity: isDarkTheme ? 0.50 : 0.48
            )

            nebulaCloud(
                color: isDarkTheme
                    ? Color(red: 0.95, green: 0.35, blue: 0.62)
                    : Color(red: 1.00, green: 0.62, blue: 0.78),
                center: UnitPoint(x: 0.82, y: 0.84),
                radius: 420,
                opacity: isDarkTheme ? 0.42 : 0.50
            )

            // 4. 별빛 — 라이트 모드에서도 보이도록 톤 조정
            StarfieldView()
                .opacity(isDarkTheme ? 0.95 : 0.55)
                .blendMode(isDarkTheme ? .screen : .plusDarker)
                .colorMultiply(
                    isDarkTheme
                        ? .white
                        : Color(red: 0.32, green: 0.28, blue: 0.55)
                )

            // 5. 외곽 비네팅 — 우주의 깊이감
            RadialGradient(
                colors: [
                    .clear,
                    (isDarkTheme ? Color.black : Color(red: 0.22, green: 0.18, blue: 0.42))
                        .opacity(isDarkTheme ? 0.50 : 0.18)
                ],
                center: .center,
                startRadius: 240,
                endRadius: 760
            )
        }
        .ignoresSafeArea()
        .animation(.easeInOut(duration: 0.32), value: isDarkTheme)
    }

    @ViewBuilder
    private func nebulaCloud(color: Color, center: UnitPoint, radius: CGFloat, opacity: Double) -> some View {
        RadialGradient(
            colors: [color.opacity(opacity), color.opacity(opacity * 0.35), .clear],
            center: center,
            startRadius: 8,
            endRadius: radius
        )
        .blendMode(isDarkTheme ? .screen : .plusLighter)
    }

    private var lightBaseColors: [Color] {
        [
            Color(red: 0.85, green: 0.89, blue: 1.00),  // periwinkle
            Color(red: 0.94, green: 0.88, blue: 1.00),  // pale lavender
            Color(red: 0.99, green: 0.91, blue: 0.95)   // soft rose
        ]
    }

    private var darkBaseColors: [Color] {
        [
            Color(red: 0.02, green: 0.03, blue: 0.10),
            Color(red: 0.05, green: 0.04, blue: 0.18),
            Color(red: 0.01, green: 0.01, blue: 0.06)
        ]
    }
}

// MARK: - Logo Pulse View

private struct ZeroLogoView: View {
    let isThinking: Bool
    @State private var pulse = false

    var body: some View {
        Image("AppLogo")
            .resizable()
            .scaledToFit()
            .frame(width: 220, height: 220)
            .scaleEffect(pulse ? (isThinking ? 1.07 : 1.03) : 1.0)
            .shadow(
                color: isThinking
                    ? Color(red: 0.60, green: 0.35, blue: 0.85).opacity(0.50)
                    : Color(red: 0.294, green: 0.561, blue: 0.831).opacity(0.35),
                radius: isThinking ? 28 : 18
            )
            .animation(
                .easeInOut(duration: isThinking ? 0.85 : 1.9).repeatForever(autoreverses: true),
                value: pulse
            )
            .animation(.easeInOut(duration: 0.4), value: isThinking)
            .onAppear { pulse = true }
    }
}

// MARK: - Conversation Overlay

private struct ConversationOverlay: View {
    let messages: [Message]
    let isLoading: Bool
    let alphaBlue: Color
    let betaPink: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(messages.enumerated()), id: \.element.id) { idx, msg in
                HoloBubble(message: msg, alphaBlue: alphaBlue, betaPink: betaPink)
                    .opacity(fadeOpacity(index: idx, total: messages.count))
            }
            if isLoading {
                HoloTypingIndicator(alphaBlue: alphaBlue, betaPink: betaPink)
            }
        }
        .frame(maxWidth: 560)
    }

    private func fadeOpacity(index: Int, total: Int) -> Double {
        guard total > 1 else { return 1.0 }
        switch total - 1 - index {
        case 0: return 1.0
        case 1: return 0.55
        default: return 0.22
        }
    }
}

// MARK: - Holo Bubble

private struct HoloBubble: View {
    let message: Message
    let alphaBlue: Color
    let betaPink: Color

    private var isUser: Bool { message.isUser }

    private var accentColor: Color {
        if isUser { return Color(red: 0.15, green: 0.28, blue: 0.52) }
        switch message.persona {
        case .alpha: return alphaBlue
        case .beta:  return betaPink
        case .none:  return alphaBlue
        }
    }

    private var fillColor: Color {
        if isUser { return Color(red: 0.15, green: 0.28, blue: 0.52).opacity(0.08) }
        switch message.persona {
        case .alpha: return alphaBlue.opacity(0.10)
        case .beta:  return betaPink.opacity(0.10)
        case .none:  return Color.primary.opacity(0.05)
        }
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
                    .foregroundStyle(accentColor.opacity(0.75))
                    .tracking(2)

                Text(message.content)
                    .font(.system(size: 12.5))
                    .foregroundStyle(Color.primary.opacity(0.85))
                    .lineLimit(5)
                    .multilineTextAlignment(isUser ? .trailing : .leading)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 9)
                    .background(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .fill(fillColor)
                            .overlay(
                                RoundedRectangle(cornerRadius: 12, style: .continuous)
                                    .strokeBorder(accentColor.opacity(0.3), lineWidth: 1)
                            )
                    )
                    .background(
                        .ultraThinMaterial.opacity(0.5),
                        in: RoundedRectangle(cornerRadius: 12, style: .continuous)
                    )
            }

            if !isUser { Spacer(minLength: 48) }
        }
    }
}

// MARK: - Typing Indicator

private struct HoloTypingIndicator: View {
    let alphaBlue: Color
    let betaPink: Color
    @State private var phase = false

    var body: some View {
        HStack(spacing: 10) {
            HStack(spacing: 5) {
                ForEach(0..<3, id: \.self) { i in
                    Circle()
                        .fill(i % 2 == 0 ? alphaBlue : betaPink)
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
                    .fill(alphaBlue.opacity(0.08))
                    .overlay(
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .strokeBorder(alphaBlue.opacity(0.25), lineWidth: 1)
                    )
            )

            Text("ALPHA · BETA PROCESSING")
                .font(.system(size: 8, design: .monospaced))
                .foregroundStyle(alphaBlue.opacity(0.55))
                .tracking(2)

            Spacer()
        }
        .onAppear { phase = true }
    }
}
