import Foundation
import Vision
import AppKit

struct VBox: Codable {
    let x: Double
    let y: Double
    let w: Double
    let h: Double
    let confidence: Double
}

struct VLine: Codable {
    let text: String
    let confidence: Double
    let y: Double
}

struct VResult: Codable {
    let file: String
    let width: Int
    let height: Int
    let text: [VLine]
    let faces: [VBox]
    let salient: [VBox]
}

func normalizeBox(_ box: CGRect, confidence: Double) -> VBox {
    VBox(
        x: Double(box.minX),
        y: Double(1.0 - box.maxY),
        w: Double(box.width),
        h: Double(box.height),
        confidence: confidence
    )
}

func analyze(_ url: URL) -> VResult {
    let empty = VResult(file: url.lastPathComponent, width: 0, height: 0, text: [], faces: [], salient: [])
    guard
        let image = NSImage(contentsOf: url),
        let tiff = image.tiffRepresentation,
        let rep = NSBitmapImageRep(data: tiff),
        let cg = rep.cgImage
    else { return empty }

    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    var lines: [VLine] = []
    var faces: [VBox] = []
    var salient: [VBox] = []

    let textRequest = VNRecognizeTextRequest()
    textRequest.recognitionLanguages = ["zh-Hans", "en-US"]
    textRequest.recognitionLevel = .accurate
    textRequest.usesLanguageCorrection = false
    if (try? handler.perform([textRequest])) != nil {
        var seen = Set<String>()
        for observation in textRequest.results ?? [] {
            guard let candidate = observation.topCandidates(1).first else { continue }
            let value = candidate.string.trimmingCharacters(in: .whitespacesAndNewlines)
            if value.isEmpty || seen.contains(value) { continue }
            seen.insert(value)
            lines.append(VLine(
                text: value,
                confidence: Double(candidate.confidence),
                y: Double(1.0 - observation.boundingBox.maxY)
            ))
        }
        lines.sort { $0.y < $1.y }
    }

    let faceRequest = VNDetectFaceRectanglesRequest()
    if (try? handler.perform([faceRequest])) != nil {
        for face in faceRequest.results ?? [] {
            faces.append(normalizeBox(face.boundingBox, confidence: Double(face.confidence)))
        }
    }

    let saliencyRequest = VNGenerateAttentionBasedSaliencyImageRequest()
    if (try? handler.perform([saliencyRequest])) != nil,
       let observation = saliencyRequest.results?.first as? VNSaliencyImageObservation,
       let objects = observation.salientObjects {
        for object in objects {
            salient.append(normalizeBox(object.boundingBox, confidence: Double(object.confidence)))
        }
    }

    return VResult(
        file: url.lastPathComponent,
        width: cg.width,
        height: cg.height,
        text: lines,
        faces: faces,
        salient: salient
    )
}

let arguments = CommandLine.arguments
guard arguments.count > 1 else {
    FileHandle.standardError.write(Data("usage: vision_probe <image-dir>\n".utf8))
    exit(2)
}

let directory = URL(fileURLWithPath: arguments[1], isDirectory: true)
let manager = FileManager.default
let files = ((try? manager.contentsOfDirectory(
    at: directory,
    includingPropertiesForKeys: nil,
    options: [.skipsHiddenFiles]
)) ?? [])
    .filter { $0.pathExtension.lowercased() == "jpg" }
    .sorted { $0.lastPathComponent < $1.lastPathComponent }

var results = [VResult?](repeating: nil, count: files.count)
let lock = NSLock()

DispatchQueue.concurrentPerform(iterations: files.count) { index in
    let result = analyze(files[index])
    lock.lock()
    results[index] = result
    lock.unlock()
}

let encoder = JSONEncoder()
for result in results {
    guard let result, let data = try? encoder.encode(result),
          let line = String(data: data, encoding: .utf8) else { continue }
    print(line)
}
