import SwiftUI

struct PersonaSelector: View {
    @Binding var selected: Persona

    var body: some View {
        HStack(spacing: 0) {
            ForEach(Persona.allCases) { persona in
                Button(persona.displayName) {
                    selected = persona
                }
                .buttonStyle(.plain)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(selected == persona ? Color.accentColor : Color.clear)
                .foregroundStyle(selected == persona ? Color.white : Color.primary)
                .clipShape(RoundedRectangle(cornerRadius: 6))
            }
        }
        .padding(3)
        .background(Color(nsColor: .separatorColor).opacity(0.3))
        .clipShape(RoundedRectangle(cornerRadius: 9))
    }
}
