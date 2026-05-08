import Foundation

struct ClaudeService {
    private let apiKey: String
    private let apiURL = URL(string: "https://api.anthropic.com/v1/messages")!
    static let model = "claude-sonnet-4-6"

    init(apiKey: String) {
        self.apiKey = apiKey
    }

    func send(history: [(role: String, content: String)], persona: Persona) async throws -> String {
        guard !apiKey.isEmpty else {
            throw ClaudeError.missingAPIKey
        }

        let requestBody = RequestBody(
            model: Self.model,
            maxTokens: 1024,
            system: persona.systemPrompt,
            messages: history.map { APIMessage(role: $0.role, content: $0.content) }
        )

        var request = URLRequest(url: apiURL)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(apiKey, forHTTPHeaderField: "x-api-key")
        request.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version")
        request.httpBody = try JSONEncoder().encode(requestBody)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            if let body = String(data: data, encoding: .utf8) {
                throw ClaudeError.apiError(body)
            }
            throw ClaudeError.apiError("알 수 없는 오류")
        }

        let decoded = try JSONDecoder().decode(ResponseBody.self, from: data)
        return decoded.content.first(where: { $0.type == "text" })?.text ?? ""
    }

    enum ClaudeError: LocalizedError {
        case missingAPIKey
        case apiError(String)

        var errorDescription: String? {
            switch self {
            case .missingAPIKey:
                return "API 키가 없습니다. 설정에서 입력해주세요."
            case .apiError(let msg):
                return "API 오류: \(msg)"
            }
        }
    }

    private struct RequestBody: Encodable {
        let model: String
        let maxTokens: Int
        let system: String
        let messages: [APIMessage]

        enum CodingKeys: String, CodingKey {
            case model, system, messages
            case maxTokens = "max_tokens"
        }
    }

    private struct APIMessage: Encodable {
        let role: String
        let content: String
    }

    private struct ResponseBody: Decodable {
        let content: [ContentBlock]

        struct ContentBlock: Decodable {
            let type: String
            let text: String
        }
    }
}
