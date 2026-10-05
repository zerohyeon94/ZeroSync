import Foundation
import SwiftData

@Model
final class Message {
    var id: UUID
    var content: String
    var isUser: Bool
    var personaRaw: String?
    var timestamp: Date

    var persona: Persona? {
        guard let raw = personaRaw else { return nil }
        return Persona(rawValue: raw)
    }

    init(content: String, isUser: Bool, persona: Persona? = nil) {
        self.id = UUID()
        self.content = content
        self.isUser = isUser
        self.personaRaw = persona?.rawValue
        self.timestamp = Date()
    }
}
