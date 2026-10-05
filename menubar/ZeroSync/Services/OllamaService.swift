import Foundation

struct OllamaService {
    static let defaultModel = "qwen3:14b"
    private static let baseURL = URL(string: "http://localhost:11434")!

    static var model: String {
        let stored = UserDefaults.standard.string(forKey: "ollamaModel") ?? ""
        return stored.isEmpty ? defaultModel : stored
    }

    func send(
        history: [(role: String, content: String)],
        persona: Persona,
        knowledge: String?
    ) async throws -> String {
        var system = persona.systemPrompt(with: UserContext.load())
        if let knowledge, !knowledge.isEmpty {
            system += "\n\n" + knowledge
        }

        let requestBody = ChatRequest(
            model: Self.model,
            messages: [APIMessage(role: "system", content: system)]
                + history.map { APIMessage(role: $0.role, content: $0.content) },
            stream: false,
            options: .init(numPredict: 1024)
        )

        var request = URLRequest(url: Self.baseURL.appendingPathComponent("api/chat"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 300
        request.httpBody = try JSONEncoder().encode(requestBody)

        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch let error as URLError where error.code == .cannotConnectToHost || error.code == .cannotFindHost {
            throw OllamaError.notRunning
        }

        guard let http = response as? HTTPURLResponse else {
            throw OllamaError.apiError("알 수 없는 응답")
        }

        guard http.statusCode == 200 else {
            let body = String(data: data, encoding: .utf8) ?? ""
            if http.statusCode == 404 || body.contains("not found") {
                throw OllamaError.modelNotInstalled(Self.model)
            }
            throw OllamaError.apiError(body)
        }

        let decoded = try JSONDecoder().decode(ChatResponse.self, from: data)
        return Self.stripThinking(decoded.message.content)
    }

    /// 설치된 모델 목록 조회 (설정 화면용). 서버 미실행 시 OllamaError.notRunning.
    static func listModels() async throws -> [String] {
        var request = URLRequest(url: baseURL.appendingPathComponent("api/tags"))
        request.timeoutInterval = 5

        let data: Data
        do {
            (data, _) = try await URLSession.shared.data(for: request)
        } catch {
            throw OllamaError.notRunning
        }

        let decoded = try JSONDecoder().decode(TagsResponse.self, from: data)
        return decoded.models.map(\.name).sorted()
    }

    /// qwen3 등 추론 모델이 출력하는 <think>...</think> 블록 제거
    private static func stripThinking(_ text: String) -> String {
        var result = text
        while let start = result.range(of: "<think>"),
              let end = result.range(of: "</think>", range: start.upperBound..<result.endIndex) {
            result.removeSubrange(start.lowerBound..<end.upperBound)
        }
        return result.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    enum OllamaError: LocalizedError {
        case notRunning
        case modelNotInstalled(String)
        case apiError(String)

        var errorDescription: String? {
            switch self {
            case .notRunning:
                return "Ollama가 실행 중이 아닙니다. ollama.com에서 설치 후 실행해주세요."
            case .modelNotInstalled(let model):
                return "모델이 설치되지 않았습니다. 터미널에서 'ollama pull \(model)'을 실행해주세요."
            case .apiError(let msg):
                return "Ollama 오류: \(msg)"
            }
        }
    }

    private struct ChatRequest: Encodable {
        let model: String
        let messages: [APIMessage]
        let stream: Bool
        let options: Options

        struct Options: Encodable {
            let numPredict: Int

            enum CodingKeys: String, CodingKey {
                case numPredict = "num_predict"
            }
        }
    }

    private struct APIMessage: Encodable {
        let role: String
        let content: String
    }

    private struct ChatResponse: Decodable {
        let message: ResponseMessage

        struct ResponseMessage: Decodable {
            let content: String
        }
    }

    private struct TagsResponse: Decodable {
        let models: [ModelInfo]

        struct ModelInfo: Decodable {
            let name: String
        }
    }
}
