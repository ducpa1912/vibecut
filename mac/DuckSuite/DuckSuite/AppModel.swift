import AppKit
import AVFoundation
import Foundation
import Security
import SwiftUI
import UniformTypeIdentifiers

struct Project: Decodable, Identifiable {
    let id: String
    let name: String
    let sourcePath: String
    let sourceBytes: Int
    let created: Double
    let updated: Double

    enum CodingKeys: String, CodingKey {
        case id, name, created, updated
        case sourcePath = "source_path"
        case sourceBytes = "source_bytes"
    }
}

private struct ProjectList: Decodable {
    let projects: [Project]
}

private struct ProjectEnvelope: Decodable {
    let project: Project
}

@MainActor
final class AppModel: ObservableObject {
    @Published var url: URL?
    @Published var error: String?
    @Published var projects: [Project] = []
    @Published var isImporting = false
    @Published var notice: String?

    private var sidecar: Sidecar?
    private var baseURL: URL?
    private var launchToken: String?
    private var dataRoot: URL?
    private var isStarting = false
    private var recorder: AVAudioRecorder?
    private var recordingURL: URL?

    init() {
        NotificationCenter.default.addObserver(
            forName: NSApplication.willTerminateNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated { self?.stop() }
        }
    }

    func start() async {
        guard url == nil, error == nil, !isStarting else { return }
        isStarting = true
        defer { isStarting = false }
        do {
            let token = Self.randomToken()
            let root = try Self.dataRoot()
            let sidecar = try Sidecar(token: token, dataRoot: root)
            let session = try sidecar.start()
            self.sidecar = sidecar
            self.baseURL = session.baseURL
            self.launchToken = session.token
            self.dataRoot = root
            self.url = session.launchURL
            await loadProjects()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func startRecording() async throws -> String {
        guard let dataRoot else { throw ImportError.noDataRoot }
        let granted = await AVCaptureDevice.requestAccess(for: .audio)
        guard granted else {
            throw SidecarError.failedToStart("Microphone access is off. Allow it in System Settings > Privacy & Security > Microphone.")
        }
        let folder = dataRoot.appendingPathComponent("recordings", isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let url = folder.appendingPathComponent("recording-\(UUID().uuidString.lowercased()).wav")
        let settings: [String: Any] = [
            AVFormatIDKey: Int(kAudioFormatLinearPCM),
            AVSampleRateKey: 48_000,
            AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsFloatKey: false,
        ]
        recorder = try AVAudioRecorder(url: url, settings: settings)
        recordingURL = url
        guard recorder?.record() == true else {
            throw SidecarError.failedToStart("The microphone could not start recording.")
        }
        return url.path
    }

    func stopRecording() -> String? {
        recorder?.stop()
        recorder = nil
        defer { recordingURL = nil }
        guard let url = recordingURL, FileManager.default.fileExists(atPath: url.path) else {
            return nil
        }
        return url.path
    }

    func stop() {
        sidecar?.stop()
        sidecar = nil
        baseURL = nil
        launchToken = nil
        url = nil
        error = nil
    }

    func loadProjects() async {
        do {
            let data = try await request(path: "api/projects")
            projects = try JSONDecoder().decode(ProjectList.self, from: data).projects
        } catch {
            notice = "Could not load projects: \(error.localizedDescription)"
        }
    }

    func importVideo(mode: String = "new", projectID: String? = nil) async -> Bool {
        guard !isImporting else { return false }
        notice = nil
        let panel = NSOpenPanel()
        panel.title = projectID == nil ? "Import a video" : "Add a video to this project"
        panel.message = projectID == nil
            ? "MP4, MOV or M4V. The file is copied into DuckSuite."
            : "MP4, MOV or M4V. The project keeps its existing scenes."
        panel.prompt = "Import"
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowsMultipleSelection = false
        panel.allowedContentTypes = [.movie, .mpeg4Movie, .quickTimeMovie]

        guard panel.runModal() == .OK, let source = panel.url else {
            return false
        }
        return await importVideo(at: source, mode: mode, projectID: projectID)
    }

    /// Copy a user-chosen model folder into app data so the sandboxed core can read it.
    /// No model is named here: any CTranslate2 folder with the three files works.
    func chooseModelFolder() async -> (path: String?, error: String?) {
        let panel = NSOpenPanel()
        panel.title = "Choose a model folder"
        panel.message = "A CTranslate2 folder with model.bin, config.json and sentencepiece.bpe.model. It is copied into DuckSuite."
        panel.prompt = "Use Folder"
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let source = panel.url else {
            return (nil, nil)
        }
        guard let dataRoot else {
            return (nil, "DuckSuite has no data folder.")
        }
        let scoped = source.startAccessingSecurityScopedResource()
        defer { if scoped { source.stopAccessingSecurityScopedResource() } }
        let required = ["model.bin", "config.json", "sentencepiece.bpe.model"]
        let missing = required.filter {
            !FileManager.default.fileExists(
                atPath: source.appendingPathComponent($0).path
            )
        }
        guard missing.isEmpty else {
            return (nil, "Missing \(missing.joined(separator: ", ")).")
        }
        let name = source.lastPathComponent.trimmingCharacters(in: .whitespacesAndNewlines)
        let folder = name.isEmpty ? "custom" : name
        let target = dataRoot
            .appendingPathComponent("models", isDirectory: true)
            .appendingPathComponent("translation", isDirectory: true)
            .appendingPathComponent(folder, isDirectory: true)
        do {
            try FileManager.default.createDirectory(
                at: target.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            if FileManager.default.fileExists(atPath: target.path) {
                try FileManager.default.removeItem(at: target)
            }
            try FileManager.default.copyItem(at: source, to: target)
            return (target.path, nil)
        } catch {
            return (nil, error.localizedDescription)
        }
    }

    /// Copy a user's fill model folder into app data so the sandboxed core can read it.
    /// No model is named: any folder with model.onnx or model.pt works.
    func chooseFillModelFolder() async -> (path: String?, error: String?) {
        let panel = NSOpenPanel()
        panel.title = "Choose a fill model folder"
        panel.message = "A folder with model.onnx (image, mask) or model.pt (TorchScript). It is copied into DuckSuite."
        panel.prompt = "Use Folder"
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let source = panel.url else {
            return (nil, nil)
        }
        guard let dataRoot else {
            return (nil, "DuckSuite has no data folder.")
        }
        let scoped = source.startAccessingSecurityScopedResource()
        defer { if scoped { source.stopAccessingSecurityScopedResource() } }
        let found = ["model.onnx", "model.pt"].filter {
            FileManager.default.fileExists(
                atPath: source.appendingPathComponent($0).path
            )
        }
        guard !found.isEmpty else {
            return (nil, "That folder needs a model.onnx or model.pt file.")
        }
        let name = source.lastPathComponent.trimmingCharacters(in: .whitespacesAndNewlines)
        let folder = name.isEmpty ? "custom" : name
        let target = dataRoot
            .appendingPathComponent("models", isDirectory: true)
            .appendingPathComponent("fill-custom", isDirectory: true)
            .appendingPathComponent(folder, isDirectory: true)
        do {
            try FileManager.default.createDirectory(
                at: target.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            if FileManager.default.fileExists(atPath: target.path) {
                try FileManager.default.removeItem(at: target)
            }
            try FileManager.default.copyItem(at: source, to: target)
            return (target.path, nil)
        } catch {
            return (nil, error.localizedDescription)
        }
    }

    /// Import a file already granted to the app, such as a Finder drag.
    func importVideo(at source: URL, mode: String = "new", projectID: String? = nil) async -> Bool {
        guard !isImporting else { return false }
        notice = nil
        isImporting = true
        defer { isImporting = false }
        let scoped = source.startAccessingSecurityScopedResource()
        defer { if scoped { source.stopAccessingSecurityScopedResource() } }

        do {
            guard let dataRoot else { throw ImportError.noDataRoot }
            let folder = dataRoot
                .appendingPathComponent("imports", isDirectory: true)
                .appendingPathComponent(UUID().uuidString.lowercased(), isDirectory: true)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            var keepCopy = false
            defer {
                if !keepCopy {
                    try? FileManager.default.removeItem(at: folder)
                }
            }
            let ext = source.pathExtension.isEmpty ? "mp4" : source.pathExtension.lowercased()
            let target = folder.appendingPathComponent("source.\(ext)")
            try FileManager.default.copyItem(at: source, to: target)

            if let projectID, !projectID.isEmpty, mode == "scenes" || mode == "full" {
                let started = try await request(
                    path: "api/projects/\(projectID)/append/job",
                    method: "POST",
                    body: try JSONSerialization.data(withJSONObject: [
                        "source_path": target.path,
                        "mode": mode,
                        "cleanup": true,
                    ]),
                    timeout: 30
                )
                guard
                    let object = try JSONSerialization.jsonObject(with: started) as? [String: Any],
                    let job = object["job"] as? [String: Any],
                    let jobID = job["id"] as? String
                else {
                    throw ImportError.badResponse
                }
                keepCopy = true
                let completed = try await waitForAppendJob(projectID: projectID, jobID: jobID)
                await loadProjects()
                let added = mode == "scenes"
                    ? "Added scenes from \(source.lastPathComponent)"
                    : "Added the full video \(source.lastPathComponent)"
                if let warning = completed["warning"] as? String, !warning.isEmpty {
                    notice = "\(added). \(warning)"
                } else {
                    notice = added
                }
                return true
            }
            _ = try await request(
                path: "api/projects",
                method: "POST",
                body: try JSONSerialization.data(withJSONObject: [
                    "name": source.deletingPathExtension().lastPathComponent,
                    "source_path": target.path,
                ])
            )
            keepCopy = true
            await loadProjects()
            notice = "Imported \(source.lastPathComponent)"
            return true
        } catch {
            notice = "Import failed: \(error.localizedDescription)"
            return false
        }
    }

    private func waitForAppendJob(projectID: String, jobID: String) async throws -> [String: Any] {
        var consecutiveErrors = 0
        for _ in 0..<7200 {
            let data: Data
            do {
                data = try await request(
                    path: "api/projects/\(projectID)/append/job/\(jobID)",
                    timeout: 30
                )
                consecutiveErrors = 0
            } catch {
                consecutiveErrors += 1
                if consecutiveErrors >= 8 {
                    throw error
                }
                try await Task.sleep(nanoseconds: 1_000_000_000)
                continue
            }
            guard
                let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                let job = object["job"] as? [String: Any]
            else {
                throw ImportError.badResponse
            }
            switch job["state"] as? String {
            case "done":
                return job
            case "failed":
                throw ImportError.server((job["error"] as? String) ?? "Import failed.")
            default:
                try await Task.sleep(nanoseconds: 1_000_000_000)
            }
        }
        throw ImportError.server("The import took too long.")
    }

    func deleteProject(_ project: Project) async {
        do {
            _ = try await request(
                path: "api/projects/\(project.id)",
                method: "DELETE"
            )
            await loadProjects()
        } catch {
            notice = "Delete failed: \(error.localizedDescription)"
        }
    }

    private func request(
        path: String,
        method: String = "GET",
        body: Data? = nil,
        timeout: TimeInterval = 60
    ) async throws -> Data {
        guard let baseURL, let launchToken else { throw ImportError.notReady }
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = method
        request.timeoutInterval = timeout
        request.setValue("Bearer \(launchToken)", forHTTPHeaderField: "Authorization")
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw ImportError.badResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            let detail = String(data: data, encoding: .utf8) ?? "HTTP \(http.statusCode)"
            throw ImportError.server(detail)
        }
        return data
    }

    private static func randomToken() -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        let status = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        precondition(status == errSecSuccess, "Could not create a launch token.")
        return bytes.map { String(format: "%02x", $0) }.joined()
    }

    private static func dataRoot() throws -> URL {
        let support = try FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        let root = support.appendingPathComponent("DuckSuite", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        return root
    }
}

private enum ImportError: LocalizedError {
    case notReady
    case noDataRoot
    case badResponse
    case server(String)

    var errorDescription: String? {
        switch self {
        case .notReady:
            return "The local core is not ready."
        case .noDataRoot:
            return "The DuckSuite data folder is missing."
        case .badResponse:
            return "The local core returned an invalid response."
        case .server(let detail):
            return detail
        }
    }
}
