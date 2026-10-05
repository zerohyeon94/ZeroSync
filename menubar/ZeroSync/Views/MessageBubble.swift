import SwiftUI

struct MessageBubble: View {
    let message: Message

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            if message.isUser {
                Spacer(minLength: 40)
                Text(message.content)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color.accentColor)
                    .foregroundStyle(.white)
                    .clipShape(BubbleShape(isUser: true))
            } else {
                VStack(alignment: .leading, spacing: 4) {
                    if let persona = message.persona {
                        Text(persona.displayName)
                            .font(.caption2)
                            .fontWeight(.semibold)
                            .foregroundStyle(.secondary)
                    }
                    Text(message.content)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(Color(nsColor: .controlBackgroundColor))
                        .clipShape(BubbleShape(isUser: false))
                }
                Spacer(minLength: 40)
            }
        }
    }
}

private struct BubbleShape: Shape {
    let isUser: Bool

    func path(in rect: CGRect) -> Path {
        let radius: CGFloat = 12
        let smallRadius: CGFloat = 4

        var path = Path()
        if isUser {
            path.addRoundedRect(
                in: rect,
                cornerRadii: RectangleCornerRadii(
                    topLeading: radius,
                    bottomLeading: radius,
                    bottomTrailing: smallRadius,
                    topTrailing: radius
                )
            )
        } else {
            path.addRoundedRect(
                in: rect,
                cornerRadii: RectangleCornerRadii(
                    topLeading: smallRadius,
                    bottomLeading: radius,
                    bottomTrailing: radius,
                    topTrailing: radius
                )
            )
        }
        return path
    }
}
