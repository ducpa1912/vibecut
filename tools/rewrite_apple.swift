// On-device script rewrite helper (macOS 26, Apple Foundation Models).
// stdin: {"mode":"clean|short|punchy","lines":["...","..."]}
// stdout: ["...","..."]  exit 3 when Apple Intelligence is unavailable.

import Foundation
#if canImport(FoundationModels)
import FoundationModels
#endif

struct Payload: Decodable {
    let mode: String
    let lines: [String]
}

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(3)
}

func array(from text: String) -> [String]? {
    guard let start = text.firstIndex(of: "["), let end = text.lastIndex(of: "]") else { return nil }
    guard let data = String(text[start...end]).data(using: .utf8) else { return nil }
    return try? JSONDecoder().decode([String].self, from: data)
}

@main
struct RewriteApple {
    static func main() async {
        #if canImport(FoundationModels)
        if #available(macOS 26.0, *) {
            guard case .available = SystemLanguageModel.default.availability else {
                fail("Apple Intelligence is unavailable. Enable it in System Settings.")
            }
            let data = FileHandle.standardInput.readDataToEndOfFile()
            guard let payload = try? JSONDecoder().decode(Payload.self, from: data) else {
                fail("bad payload")
            }
            if payload.lines.isEmpty {
                print("[]")
                exit(0)
            }
            let style: String
            switch payload.mode {
            case "short": style = "Make every line shorter and tighter, keeping the meaning."
            case "punchy": style = "Make every line punchier and more direct, keeping the meaning."
            default: style = "Remove filler words and false starts; keep the meaning and tone."
            }
            let instructions = """
            You edit subtitle scripts. Rewrite every numbered line. \(style) \
            Keep the same line count and return a JSON array of strings only. \
            Do not add commentary, quotes or numbering.
            """
            let session = LanguageModelSession(instructions: instructions)
            let numbered = payload.lines.enumerated()
                .map { "\($0.offset + 1). \($0.element)" }
                .joined(separator: "\n")
            if let response = try? await session.respond(to: numbered),
               let values = array(from: response.content),
               values.count == payload.lines.count {
                print(String(data: try! JSONEncoder().encode(values), encoding: .utf8)!)
                exit(0)
            }
            var values: [String] = []
            for line in payload.lines {
                guard let response = try? await session.respond(to: "\(style)\nLine: \(line)") else {
                    fail("Apple Intelligence could not rewrite this script.")
                }
                values.append(response.content.trimmingCharacters(in: .whitespacesAndNewlines))
            }
            print(String(data: try! JSONEncoder().encode(values), encoding: .utf8)!)
            exit(0)
        }
        #endif
        fail("Apple Intelligence requires macOS 26 with Apple Intelligence enabled.")
    }
}
