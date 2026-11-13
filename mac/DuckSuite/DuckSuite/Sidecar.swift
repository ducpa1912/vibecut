import Darwin
import Foundation

enum SidecarError: LocalizedError {
    case missingHelper
    case invalidHandshake
    case failedToStart(String)

    var errorDescription: String? {
        switch self {
        case .missingHelper:
            return "The DuckSuite local core is missing from the app bundle."
        case .invalidHandshake:
            return "The DuckSuite local core did not return a valid port."
        case .failedToStart(let detail):
            return "The DuckSuite local core could not start. \(detail)"
        }
    }
}

struct SidecarSession {
    let baseURL: URL
    let launchURL: URL
    let token: String
}

final class Sidecar {
    private let process = Process()
    private let stdout = Pipe()
    private let stderr = Pipe()
    private let stdin = Pipe()
    private let token: String
    private let dataRoot: URL

    init(token: String, dataRoot: URL) throws {
        self.token = token
        self.dataRoot = dataRoot

        let bundle = Bundle.main.bundleURL
        let resources = bundle.appendingPathComponent("Contents/Resources/duckcore/duckcore")
        let helper = bundle.appendingPathComponent("Contents/Helpers/duckcore")
        let resourceHelpers = bundle.appendingPathComponent("Contents/Resources/Helpers/duckcore")
        let executable = FileManager.default.isExecutableFile(atPath: resources.path)
            ? resources
            : FileManager.default.isExecutableFile(atPath: helper.path)
                ? helper
                : resourceHelpers
        guard FileManager.default.isExecutableFile(atPath: executable.path) else {
            throw SidecarError.missingHelper
        }

        process.executableURL = executable
        process.arguments = ["--data-root", dataRoot.path, "--port", "0"]
        var environment = ProcessInfo.processInfo.environment
        environment["DUCK_STATIC_DIR"] = bundle
            .appendingPathComponent("Contents/Resources/static/duck")
            .path
        environment["DUCK_FILL_MODELS"] = bundle
            .appendingPathComponent("Contents/Resources/base-models")
            .path
        let helpers = FileManager.default.fileExists(
            atPath: bundle.appendingPathComponent("Contents/Helpers").path
        )
            ? bundle.appendingPathComponent("Contents/Helpers")
            : bundle.appendingPathComponent("Contents/Resources/Helpers")
        environment["DUCK_HELPER_DIR"] = helpers.path
        environment["DUCK_SWIFT_DIR"] = bundle
            .appendingPathComponent("Contents/Resources/swift")
            .path
        process.environment = environment
        process.standardOutput = stdout
        process.standardError = stderr
        process.standardInput = stdin
    }

    func start() throws -> SidecarSession {
        do {
            try process.run()

            let input = stdin.fileHandleForWriting
            try input.write(contentsOf: Data((token + "\n").utf8))
            try input.close()

            let line = try readLine(timeout: 12)
            guard
                let data = line.data(using: .utf8),
                let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                let port = object["port"] as? Int
            else {
                throw SidecarError.invalidHandshake
            }

            guard
                let baseURL = URL(string: "http://127.0.0.1:\(port)/"),
                let launchURL = URL(string: "http://127.0.0.1:\(port)/#t=\(token)")
            else {
                throw SidecarError.invalidHandshake
            }
            return SidecarSession(baseURL: baseURL, launchURL: launchURL, token: token)
        } catch {
            // The core is already running at this point: a failed handshake must
            // not leave it behind for the next attempt.
            stop()
            throw error
        }
    }

    deinit {
        stop()
    }

    func stop() {
        guard process.isRunning else { return }
        process.terminate()
        let deadline = Date().addingTimeInterval(5)
        while process.isRunning && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.05)
        }
        if process.isRunning {
            Darwin.kill(process.processIdentifier, SIGKILL)
        }
    }

    private final class HandshakeBuffer: @unchecked Sendable {
        private let lock = NSLock()
        private var data = Data()
        private var line: String?
        private var failure: String?

        func append(_ chunk: Data) -> Bool {
            lock.lock()
            defer { lock.unlock() }
            data.append(chunk)
            if let newline = data.firstIndex(of: 0x0A), line == nil {
                line = String(data: data[..<newline], encoding: .utf8)
                return true
            }
            return false
        }

        func close() {
            lock.lock()
            defer { lock.unlock() }
            if line == nil {
                failure = "The local core exited before handshake."
            }
        }

        func result() -> (line: String?, failure: String?) {
            lock.lock()
            defer { lock.unlock() }
            return (line, failure)
        }
    }

    private func readLine(timeout: TimeInterval) throws -> String {
        let semaphore = DispatchSemaphore(value: 0)
        let buffer = HandshakeBuffer()

        stdout.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if data.isEmpty {
                buffer.close()
                semaphore.signal()
                return
            }
            if buffer.append(data) {
                handle.readabilityHandler = nil
                semaphore.signal()
            }
        }

        if semaphore.wait(timeout: .now() + timeout) == .timedOut {
            stdout.fileHandleForReading.readabilityHandler = nil
            throw SidecarError.failedToStart("Timed out waiting for the local core.")
        }

        let result = buffer.result()
        if let line = result.line { return line }
        if let failure = result.failure { throw SidecarError.failedToStart(failure) }
        throw SidecarError.invalidHandshake
    }
}
