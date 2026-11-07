import Foundation
import Security
import SwiftUI

@MainActor
final class AppModel: ObservableObject {
    @Published var url: URL?
    @Published var error: String?

    private var sidecar: Sidecar?

    func start() async {
        guard url == nil, error == nil else { return }
        do {
            let token = Self.randomToken()
            let root = try Self.dataRoot()
            let sidecar = try Sidecar(token: token, dataRoot: root)
            let url = try sidecar.start()
            self.sidecar = sidecar
            self.url = url
        } catch {
            self.error = error.localizedDescription
        }
    }

    func stop() {
        sidecar?.stop()
        sidecar = nil
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
