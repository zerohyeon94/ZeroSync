import SwiftUI

struct MenuBarView: View {
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Zero-Alpha-Beta")
                    .font(.headline)
                    .fontWeight(.semibold)
                Spacer()
                Button {
                    openWindow(id: "settings")
                    NSApp.activate(ignoringOtherApps: true)
                } label: {
                    Image(systemName: "gearshape")
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 12)
            .padding(.top, 12)
            .padding(.bottom, 8)

            if let activity = ActivityMonitor.shared.current {
                HStack(spacing: 6) {
                    Circle()
                        .fill(activity.category == .productive ? Color.green :
                              activity.category == .distraction ? Color.red : Color.gray)
                        .frame(width: 8, height: 8)
                    Text("\(activity.appName)\(activity.isIdle ? " (자리 비움)" : "")")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(.horizontal, 12)
                .padding(.bottom, 8)
            }

            Divider()

            ChatView()
        }
        .frame(width: 360, height: 480)
    }
}
