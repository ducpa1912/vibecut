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

        let helper = Bundle.main.bundleURL
            .appendingPathComponent("Contents/Helpers/duckcore")
        guard FileManager.default.isExecutableFile(atPath: helper.path) else {
            throw SidecarError.missingHelper
        }

        process.executableURL = helper
        process.arguments = ["--data-root", dataRoot.path, "--port", "0"]
        process.standardOutput = stdout
        process.standardError = stderr
        process.standardInput = stdin
    }

    func start() throws -> URL {
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

        guard let url = URL(string: "http://127.0.0.1:\(port)/#t=\(token)") else {
            throw SidecarError.invalidHandshake
        }
        return url
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

    private func readLine(timeout: TimeInterval) throws -> String {
        let semaphore = DispatchSemaphore(value: 0)
        let lock = NSLock()
        var buffer = Data()
        var line: String?
        var failure: String?

        stdout.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if data.isEmpty {
                lock.lock()
                if line == nil { failure = "The local core exited before handshake." }
                lock.unlock()
                semaphore.signal()
                return
            }
            lock.lock()
            buffer.append(data)
            if let newline = buffer.firstIndex(of: 0x0A), line == nil {
                let bytes = buffer[..<newline]
                line = String(data: bytes, encoding: .utf8)
                handle.readabilityHandler = nil
                semaphore.signal()
            }
            lock.unlock()
        }

        if semaphore.wait(timeout: .now() + timeout) == .timedOut {
            stdout.fileHandleForReading.readabilityHandler = nil
            throw SidecarError.failedToStart("Timed out waiting for the local core.")
        }

        lock.lock()
        defer { lock.unlock() }
        if let line { return line }
        if let failure { throw SidecarError.failedToStart(failure) }
        throw SidecarError.invalidHandshake
    }
}
