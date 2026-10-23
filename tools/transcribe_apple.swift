// On-device transcription helper for VibeCut (macOS 26, Apple Speech framework).
// usage: transcribe_apple --audio file.wav --locale zh-CN --out transcript.json
// Output matches the Whisper shape: {language, text, segments:[{start,end,text}]}

import AVFoundation
import Foundation
import Speech

@main
struct TranscribeApple {
    static func fail(_ message: String) -> Never {
        FileHandle.standardError.write(Data((message + "\n").utf8))
        exit(3)
    }

    static func main() async {
        let args = CommandLine.arguments
        var audio = ""
        var localeID = "en-US"
        var out = ""
        var index = 1
        while index < args.count {
            switch args[index] {
            case "--audio": audio = index + 1 < args.count ? args[index + 1] : ""; index += 2
            case "--locale": localeID = index + 1 < args.count ? args[index + 1] : localeID; index += 2
            case "--out": out = index + 1 < args.count ? args[index + 1] : ""; index += 2
            default: index += 1
            }
        }
        guard !audio.isEmpty, !out.isEmpty else {
            fail("usage: --audio file --locale zh-CN --out out.json")
        }
        guard #available(macOS 26.0, *) else { fail("macOS 26 required") }
        let url = URL(fileURLWithPath: audio)
        guard FileManager.default.fileExists(atPath: url.path) else { fail("audio not found") }

        let transcriber = SpeechTranscriber(
            locale: Locale(identifier: localeID),
            transcriptionOptions: [],
            reportingOptions: [],
            attributeOptions: [.audioTimeRange],
        )
        if let request = try? await AssetInventory.assetInstallationRequest(supporting: [transcriber]) {
            do {
                try await request.downloadAndInstall()
            } catch {
                fail("speech language asset unavailable: \(error)")
            }
        }
        let analyzer = SpeechAnalyzer(modules: [transcriber])
        let file: AVAudioFile
        do {
            file = try AVAudioFile(forReading: url)
        } catch {
            fail("cannot read audio: \(error)")
        }
        do {
            try await analyzer.start(inputAudioFile: file, finishAfterFile: true)
        } catch {
            fail("analysis start failed: \(error)")
        }

        var cues: [[String: Any]] = []
        do {
            for try await result in transcriber.results {
                let text = String(result.text.characters).trimmingCharacters(in: .whitespacesAndNewlines)
                if text.isEmpty { continue }
                let start = CMTimeGetSeconds(result.range.start)
                let end = CMTimeGetSeconds(result.range.end)
                cues.append([
                    "start": start.isFinite ? start : 0,
                    "end": end.isFinite && end > start ? end : start,
                    "text": text,
                ])
            }
        } catch {
            fail("transcription stream failed: \(error)")
        }
        if cues.isEmpty { fail("no speech recognized") }

        let payload: [String: Any] = [
            "language": localeID,
            "text": cues.compactMap { $0["text"] as? String }.joined(separator: " "),
            "segments": cues,
        ]
        do {
            let data = try JSONSerialization.data(withJSONObject: payload, options: [])
            try data.write(to: URL(fileURLWithPath: out))
        } catch {
            fail("could not write output: \(error)")
        }
        exit(0)
    }
}
