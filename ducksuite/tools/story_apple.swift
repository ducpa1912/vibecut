// On-device story helper (macOS 26, Apple Foundation Models).
// stdin: {"scenes":[{"id":1,"seconds":5.0,"cue":"..."}],"count":4,"batch":0,"themes":["..."]}
// stdout: {"thesis":"...","beats":[{"id":1,"reason":"..."}]} or {"theme":"...","ids":[1,2]}
// exit 3 when Apple Intelligence is unavailable.

import Foundation
#if canImport(FoundationModels)
import FoundationModels
#endif

struct Scene: Decodable {
    let id: Int
    let seconds: Double?
    let cue: String
}

struct Payload: Decodable {
    let scenes: [Scene]
    let count: Int?
    let batch: Int?
    let themes: [String]?
}

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(3)
}

func object(from text: String) -> [String: Any]? {
    guard let start = text.firstIndex(of: "{"), let end = text.lastIndex(of: "}") else { return nil }
    guard let data = String(text[start...end]).data(using: .utf8) else { return nil }
    return try? JSONSerialization.jsonObject(with: data) as? [String: Any]
}

@main
struct StoryApple {
    static func main() async {
        if CommandLine.arguments.contains("--check") {
            var available = false
            var reason = "Apple Intelligence is unavailable."
            #if canImport(FoundationModels)
            if #available(macOS 26.0, *) {
                switch SystemLanguageModel.default.availability {
                case .available:
                    available = true
                    reason = ""
                case .unavailable(let value):
                    reason = String(describing: value)
                @unknown default:
                    reason = "unknown availability"
                }
            } else {
                reason = "requires macOS 26"
            }
            #else
            reason = "FoundationModels is not available in this SDK"
            #endif
            let payload: [String: Any] = ["available": available, "reason": reason]
            if let data = try? JSONSerialization.data(withJSONObject: payload),
               let text = String(data: data, encoding: .utf8) {
                print(text)
            }
            exit(0)
        }
        #if canImport(FoundationModels)
        if #available(macOS 26.0, *) {
            guard case .available = SystemLanguageModel.default.availability else {
                fail("Apple Intelligence is unavailable. Enable it in System Settings.")
            }
            let data = FileHandle.standardInput.readDataToEndOfFile()
            guard let payload = try? JSONDecoder().decode(Payload.self, from: data) else {
                fail("bad payload")
            }
            let numbered = payload.scenes
                .map { "\($0.id) | \(Int(($0.seconds ?? 0).rounded()))s | \($0.cue)" }
                .joined(separator: "\n")
            let batchCall = payload.batch != nil
            let instructions: String
            let body: String
            if batchCall {
                instructions = """
                You read a batch of scenes from one long video and find the beats worth keeping. \
                Return a JSON object with a short theme and two or three scene ids. No commentary.
                """
                body = "Scenes:\n\(numbered)\n\nReturn {\"theme\":\"...\",\"ids\":[1,2]}."
            } else {
                instructions = """
                You are a story editor. Choose three to six scenes that fit one narrative and \
                order them by story, not by time. They do not need to be chronological. Write one \
                bold thesis grounded in the lines, not invented facts. Return a JSON object: \
                {"thesis":"...","beats":[{"id":1,"reason":"..."}]}. No commentary, no numbering.
                """
                let themes = (payload.themes ?? []).filter { !$0.isEmpty }
                let themeText = themes.isEmpty ? "" : "Batch themes:\n" + themes.joined(separator: "\n") + "\n\n"
                body = themeText + "Scenes:\n\(numbered)\n\nPick \(payload.count ?? 4) beats in story order."
            }
            let session = LanguageModelSession(instructions: instructions)
            guard let response = try? await session.respond(to: body),
                  let value = object(from: response.content) else {
                fail("Apple Intelligence could not write a story.")
            }
            if let out = try? JSONSerialization.data(withJSONObject: value),
               let text = String(data: out, encoding: .utf8) {
                print(text)
                exit(0)
            }
            fail("Apple Intelligence returned an unreadable story.")
        }
        #endif
        fail("Apple Intelligence requires macOS 26 with Apple Intelligence enabled.")
    }
}
