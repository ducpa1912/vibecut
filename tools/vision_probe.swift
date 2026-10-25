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

struct VBounds: Codable {
    let x: Double
    let y: Double
    let w: Double
    let h: Double
}

struct VCandidate: Codable {
    let text: String
    let confidence: Double
}

struct VLine: Codable {
    let text: String
    let confidence: Double
    let y: Double
    let candidates: [VCandidate]
    let box: VBounds
}

struct VResult: Codable {
    let file: String
    let width: Int
    let height: Int
    let text: [VLine]
    let faces: [VBox]
    let salient: [VBox]
}

// Small, documented lexicon for overlay/brand text that Vision often mangles
// at thumbnail resolution. Python re-checks lexical evidence before using it.
let overlayWords = [
    "LINKTREE",
    "linktr.ee",
    "Instagram",
    "TikTok",
    "YouTube",
    "RedNote",
    "Xiaohongshu",
]

// Only retry genuinely low-confidence, small lines. Capping retries keeps a
// frame with lots of background text from becoming several extra OCR passes.
let retryConfidence = 0.45
let maxRetriesPerFrame = 4
let retryMaxPixelHeight: CGFloat = 160.0

func normalizeBox(_ box: CGRect, confidence: Double) -> VBox {
    VBox(
        x: Double(box.minX),
        y: Double(1.0 - box.maxY),
        w: Double(box.width),
        h: Double(box.height),
        confidence: confidence
    )
}

func normalizeBounds(_ box: CGRect) -> VBounds {
    VBounds(
        x: Double(box.minX),
        y: Double(1.0 - box.maxY),
        w: Double(box.width),
        h: Double(box.height)
    )
}

func makeTextRequest() -> VNRecognizeTextRequest {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.usesLanguageCorrection = true
    request.customWords = overlayWords
    return request
}

func textCandidates(from observation: VNRecognizedTextObservation) -> [VCandidate] {
    observation.topCandidates(3).compactMap { candidate in
        let value = candidate.string.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return nil }
        return VCandidate(text: value, confidence: Double(candidate.confidence))
    }
}

func mergeCandidates(_ groups: [[VCandidate]]) -> [VCandidate] {
    var best: [String: VCandidate] = [:]
    for group in groups {
        for candidate in group {
            let value = candidate.text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !value.isEmpty else { continue }
            let key = value.lowercased()
            if let current = best[key], current.confidence >= candidate.confidence {
                continue
            }
            best[key] = VCandidate(text: value, confidence: candidate.confidence)
        }
    }
    return best.values.sorted {
        if $0.confidence == $1.confidence {
            return $0.text < $1.text
        }
        return $0.confidence > $1.confidence
    }
}

func upscaledCrop(_ image: CGImage, box: CGRect) -> CGImage? {
    let imageWidth = CGFloat(image.width)
    let imageHeight = CGFloat(image.height)
    guard imageWidth > 0, imageHeight > 0 else { return nil }

    let rawX0 = box.minX * imageWidth
    let rawX1 = box.maxX * imageWidth
    let rawY0 = (1.0 - box.maxY) * imageHeight
    let rawY1 = (1.0 - box.minY) * imageHeight
    let marginX = max(2.0, (rawX1 - rawX0) * 0.12)
    let marginY = max(2.0, (rawY1 - rawY0) * 0.35)

    let x0 = max(0, Int(floor(rawX0 - marginX)))
    let x1 = min(image.width, Int(ceil(rawX1 + marginX)))
    let y0 = max(0, Int(floor(rawY0 - marginY)))
    let y1 = min(image.height, Int(ceil(rawY1 + marginY)))
    guard x1 - x0 >= 8, y1 - y0 >= 6 else { return nil }

    let cropRect = CGRect(x: x0, y: y0, width: x1 - x0, height: y1 - y0)
    guard let crop = image.cropping(to: cropRect) else { return nil }

    var scale = min(4.0, max(2.0, 96.0 / CGFloat(crop.height)))
    scale = min(
        scale,
        2400.0 / CGFloat(crop.width),
        1200.0 / CGFloat(crop.height)
    )
    guard scale >= 1.5 else { return nil }

    let targetWidth = max(1, Int((CGFloat(crop.width) * scale).rounded()))
    let targetHeight = max(1, Int((CGFloat(crop.height) * scale).rounded()))
    guard
        let colorSpace = CGColorSpace(name: CGColorSpace.sRGB),
        let context = CGContext(
            data: nil,
            width: targetWidth,
            height: targetHeight,
            bitsPerComponent: 8,
            bytesPerRow: 0,
            space: colorSpace,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        )
    else { return nil }

    context.interpolationQuality = .high
    context.draw(
        crop,
        in: CGRect(x: 0, y: 0, width: targetWidth, height: targetHeight)
    )
    return context.makeImage()
}

func retryCandidates(for box: CGRect, in image: CGImage) -> [VCandidate] {
    guard let crop = upscaledCrop(image, box: box) else { return [] }
    let request = makeTextRequest()
    let handler = VNImageRequestHandler(cgImage: crop, options: [:])
    guard (try? handler.perform([request])) != nil else { return [] }
    let all = request.results ?? []
    guard !all.isEmpty else { return [] }

    // The crop is centered on the original line. Ignore observations near the
    // margins, then join split observations left-to-right so a retry can never
    // downgrade a full line to one high-confidence word.
    let centered = all.filter { $0.boundingBox.midY >= 0.20 && $0.boundingBox.midY <= 0.80 }
    let observations = (centered.isEmpty ? all : centered).sorted {
        if abs($0.boundingBox.midY - $1.boundingBox.midY) > 0.12 {
            return $0.boundingBox.midY > $1.boundingBox.midY
        }
        return $0.boundingBox.minX < $1.boundingBox.minX
    }
    if observations.count == 1 {
        return textCandidates(from: observations[0])
    }

    var combined: [VCandidate] = []
    for rank in 0..<3 {
        var parts: [String] = []
        var confidence = 1.0
        for observation in observations {
            let candidates = observation.topCandidates(rank + 1)
            guard let candidate = candidates.last else { continue }
            let value = candidate.string.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !value.isEmpty else { continue }
            parts.append(value)
            confidence = min(confidence, Double(candidate.confidence))
        }
        guard !parts.isEmpty else { continue }
        combined.append(VCandidate(text: parts.joined(separator: " "), confidence: confidence))
    }
    return mergeCandidates([combined])
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
    var retries = 0

    let textRequest = makeTextRequest()
    if (try? handler.perform([textRequest])) != nil {
        var seen = Set<String>()
        for observation in textRequest.results ?? [] {
            let initial = textCandidates(from: observation)
            guard !initial.isEmpty else { continue }

            var merged = initial
            let pixelHeight = observation.boundingBox.height * CGFloat(cg.height)
            if
                initial[0].confidence < retryConfidence,
                retries < maxRetriesPerFrame,
                pixelHeight <= retryMaxPixelHeight
            {
                retries += 1
                let extra = retryCandidates(for: observation.boundingBox, in: cg)
                if !extra.isEmpty {
                    merged = mergeCandidates([initial, extra])
                }
            }

            let ranked = Array(merged.prefix(3))
            guard let best = ranked.first else { continue }
            let key = best.text.lowercased()
            if seen.contains(key) { continue }
            seen.insert(key)
            lines.append(VLine(
                text: best.text,
                confidence: best.confidence,
                y: Double(1.0 - observation.boundingBox.maxY),
                candidates: ranked,
                box: normalizeBounds(observation.boundingBox)
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
