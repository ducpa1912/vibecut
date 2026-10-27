// On-device transcription helper for VibeCut (macOS 26, Apple Speech framework).
// usage: transcribe_apple --audio file.wav --locale zh-CN --out transcript.json
//        [--vocabulary '["Name","Brand"]']
// Output: {language, text, segments:[{start,end,text,words:[{w,start,end,confidence}]}], words:[...]}
// Word timings come from each attributed run's .audioTimeRange (SpeechTranscriber).

import AVFoundation
import Foundation
import Speech

@main
struct TranscribeApple {
    static func fail(_ message: String) -> Never {
        FileHandle.standardError.write(Data((message + "\n").utf8))
        exit(3)
    }

    static func vocabulary(from raw: String) -> [String] {
        let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return [] }
        if value.hasPrefix("["),
           let data = value.data(using: .utf8),
           let rows = try? JSONSerialization.jsonObject(with: data) as? [String] {
            return rows.filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        }
        return value.split(separator: ",").map {
            $0.trimmingCharacters(in: .whitespacesAndNewlines)
        }.filter { !$0.isEmpty }
    }

    static func seconds(_ time: CMTime) -> Double {
        let value = CMTimeGetSeconds(time)
        return value.isFinite ? value : 0
    }

    static func main() async {
        let args = CommandLine.arguments
        var audio = ""
        var localeID = "en-US"
        var out = ""
        var vocabularyRaw = ""
        var index = 1
        while index < args.count {
            switch args[index] {
            case "--audio": audio = index + 1 < args.count ? args[index + 1] : ""; index += 2
            case "--locale": localeID = index + 1 < args.count ? args[index + 1] : localeID; index += 2
            case "--out": out = index + 1 < args.count ? args[index + 1] : ""; index += 2
            case "--vocabulary": vocabularyRaw = index + 1 < args.count ? args[index + 1] : ""; index += 2
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
            attributeOptions: [.audioTimeRange, .transcriptionConfidence],
        )
        if let request = try? await AssetInventory.assetInstallationRequest(supporting: [transcriber]) {
            do {
                try await request.downloadAndInstall()
            } catch {
                fail("speech language asset unavailable: \(error)")
            }
        }
        let analyzer = SpeechAnalyzer(modules: [transcriber])
        let terms = vocabulary(from: vocabularyRaw)
        if !terms.isEmpty {
            let context = AnalysisContext()
            context.contextualStrings[.general] = terms
            do {
                try await analyzer.setContext(context)
            } catch {
                // Contextual biasing is an accuracy hint; transcription still works.
            }
        }
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

        var segments: [[String: Any]] = []
        var allWords: [[String: Any]] = []
        do {
            for try await result in transcriber.results {
                let text = String(result.text.characters)
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if text.isEmpty { continue }
                let start = seconds(result.range.start)
                let end = seconds(result.range.end)
                var segmentWords: [[String: Any]] = []
                for run in result.text.runs {
                    let runText = String(result.text[run.range].characters)
                        .trimmingCharacters(in: .whitespacesAndNewlines)
                    if runText.isEmpty { continue }
                    var word: [String: Any] = ["w": runText]
                    if let range = run.audioTimeRange {
                        let wordStart = seconds(range.start)
                        let wordEnd = seconds(range.end)
                        word["start"] = wordStart
                        word["end"] = wordEnd > wordStart ? wordEnd : wordStart
                    } else {
                        word["start"] = start
                        word["end"] = end
                    }
                    if let confidence = run.transcriptionConfidence {
                        word["confidence"] = confidence
                    }
                    segmentWords.append(word)
                    allWords.append(word)
                }
                segments.append([
                    "start": start,
                    "end": end > start ? end : start,
                    "text": text,
                    "words": segmentWords,
                ])
            }
        } catch {
            fail("transcription stream failed: \(error)")
        }
        if segments.isEmpty { fail("no speech recognized") }

        let payload: [String: Any] = [
            "language": localeID,
            "text": segments.compactMap { $0["text"] as? String }.joined(separator: " "),
            "segments": segments,
            "words": allWords,
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
