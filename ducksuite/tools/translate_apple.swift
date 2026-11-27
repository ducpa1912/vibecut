// On-device translation helper for VibeCut.
// stdin:  {"source": "zh", "target": "en", "lines": ["...", "..."]}
// stdout: ["...", "..."]  (JSON array, same order)
//
// Order of engines:
//   1. Apple Translation framework (macOS 26 convenience init, on-device)
//   2. Apple Foundation Models (~3B LLM, macOS 26 + Apple Intelligence)
// Exits 3 when neither engine can translate, so the Python side can fall back.

import Foundation
import Translation

#if canImport(FoundationModels)
import FoundationModels
#endif

struct Payload: Decodable {
    let target: String
    let source: String?
    let targetName: String?
    let lines: [String]

    enum CodingKeys: String, CodingKey {
        case target, source, targetName, lines
    }

    var promptLanguage: String { targetName ?? target }
}

func extractJSONArray(_ text: String) -> [String]? {
    guard let start = text.firstIndex(of: "["),
          let end = text.lastIndex(of: "]"),
          start < end else { return nil }
    let slice = String(text[start...end])
    guard let data = slice.data(using: .utf8) else { return nil }
    return try? JSONDecoder().decode([String].self, from: data)
}

func emit(_ lines: [String]) -> Never {
    if let data = try? JSONEncoder().encode(lines),
       let text = String(data: data, encoding: .utf8) {
        FileHandle.standardOutput.write(Data((text + "\n").utf8))
        exit(0)
    }
    exit(4)
}

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(3)
}

func languageCode(_ raw: String?) -> String? {
    guard let raw, !raw.isEmpty else { return nil }
    return raw.split(separator: "-").first.map(String.init) ?? raw
}

func translateWithFramework(_ payload: Payload) async -> [String]? {
    guard #available(macOS 26.0, *) else { return nil }
    guard let source = languageCode(payload.source), let target = languageCode(payload.target) else {
        return nil
    }
    if source == target { return payload.lines }

    let sourceLanguage = Locale.Language(identifier: source)
    let targetLanguage = Locale.Language(identifier: target)
    let availability = LanguageAvailability()
    var status = await availability.status(from: sourceLanguage, to: targetLanguage)
    if status == .unsupported {
        FileHandle.standardError.write(Data("translation pair unsupported\n".utf8))
        return nil
    }

    let session = TranslationSession(installedSource: sourceLanguage, target: targetLanguage)
    if status == .supported {
        // Ask the system to fetch the language pack. On macOS this may be a
        // silent download; if it needs UI it fails and we fall back.
        try? await session.prepareTranslation()
        status = await availability.status(from: sourceLanguage, to: targetLanguage)
        if status != .installed {
            FileHandle.standardError.write(
                Data("translation language not installed: install it in System Settings → General → Language & Region → Translation Languages\n".utf8)
            )
            return nil
        }
    }

    do {
        let requests = payload.lines.map { TranslationSession.Request(sourceText: $0) }
        let responses = try await session.translations(from: requests)
        let texts = responses.map { $0.targetText }
        return texts.count == payload.lines.count ? texts : nil
    } catch {
        FileHandle.standardError.write(Data("translation error: \(error)\n".utf8))
        return nil
    }
}

func translateWithFoundationModels(_ payload: Payload) async -> [String]? {
    #if canImport(FoundationModels)
    if #available(macOS 26.0, *) {
        let model = SystemLanguageModel.default
        if case .available = model.availability {
            let instructions = """
            You are a precise subtitle translator. Translate every numbered \
            line into the requested language. Keep the same meaning, tone and \
            line count. Reply with a JSON array of strings only.
            """
            let session = LanguageModelSession(instructions: instructions)
            let targetName = payload.promptLanguage
            let numbered = payload.lines.enumerated()
                .map { "\($0.offset + 1). \($0.element)" }
                .joined(separator: "\n")
            if let response = try? await session.respond(to: "Translate to \(targetName):\n\(numbered)"),
               let translated = extractJSONArray(response.content),
               translated.count == payload.lines.count {
                return translated
            }
            var results: [String] = []
            for line in payload.lines {
                let prompt = "Translate to \(targetName). Reply with the translation only:\n\(line)"
                guard let response = try? await session.respond(to: prompt) else { return nil }
                results.append(response.content.trimmingCharacters(in: .whitespacesAndNewlines))
            }
            return results.count == payload.lines.count ? results : nil
        }
    }
    #endif
    return nil
}

@main
struct TranslateApple {
    static func main() async {
        let arguments = CommandLine.arguments
        if arguments.count >= 4, arguments[1] == "--check" {
            let source = Locale.Language(identifier: arguments[2])
            let target = Locale.Language(identifier: arguments[3])
            var payload: [String: String] = [
                "status": "unsupported",
                "framework": "false",
            ]
            if #available(macOS 26.0, *) {
                payload["framework"] = "true"
                let availability = LanguageAvailability()
                let status = await availability.status(from: source, to: target)
                switch status {
                case .installed: payload["status"] = "installed"
                case .supported: payload["status"] = "supported"
                default: payload["status"] = "unsupported"
                }
            }
            if let data = try? JSONEncoder().encode(payload),
               let text = String(data: data, encoding: .utf8) {
                print(text)
            }
            exit(0)
        }

        let input = FileHandle.standardInput.readDataToEndOfFile()
        guard let payload = try? JSONDecoder().decode(Payload.self, from: input) else {
            fail("bad payload")
        }
        if payload.lines.isEmpty { emit([]) }

        if let result = await translateWithFramework(payload) {
            emit(result)
        }
        if let result = await translateWithFoundationModels(payload) {
            emit(result)
        }
        fail("no on-device translation engine available")
    }
}
