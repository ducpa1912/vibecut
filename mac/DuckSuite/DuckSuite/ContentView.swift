import AppKit
import SwiftUI
import WebKit

struct ContentView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        ZStack {
            Color(nsColor: .windowBackgroundColor)
                .ignoresSafeArea()

            if let url = model.url {
                WebView(
                    url: url,
                    onImport: { await model.importVideo() },
                    onRecordStart: { try await model.startRecording() },
                    onRecordStop: { model.stopRecording() }
                )
            } else if let error = model.error {
                VStack(spacing: 14) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 28, weight: .medium))
                        .foregroundStyle(.secondary)
                    Text("DuckSuite could not start")
                        .font(.title3.weight(.semibold))
                    Text(error)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 420)
                    Button("Try again") {
                        model.error = nil
                        Task { await model.start() }
                    }
                    .buttonStyle(.borderedProminent)
                }
                .padding(32)
            } else {
                VStack(spacing: 12) {
                    ProgressView()
                    Text("Starting DuckSuite…")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .task { await model.start() }
        .onAppear { Task { await model.start() } }
        .onDisappear { model.stop() }
    }
}

private struct WebView: NSViewRepresentable {
    let url: URL
    let onImport: @MainActor () async -> Bool
    let onRecordStart: @MainActor () async throws -> String
    let onRecordStop: @MainActor () -> String?

    func makeNSView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true
        configuration.websiteDataStore = .nonPersistent()

        let controller = WKUserContentController()
        controller.add(context.coordinator, name: "duck")
        configuration.userContentController = controller

        let view = WKWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = context.coordinator
        view.underPageBackgroundColor = .clear
        context.coordinator.webView = view
        return view
    }

    func updateNSView(_ view: WKWebView, context: Context) {
        if view.url != url {
            view.load(URLRequest(url: url))
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(
            onImport: onImport,
            onRecordStart: onRecordStart,
            onRecordStop: onRecordStop
        )
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        weak var webView: WKWebView?
        private let onImport: @MainActor () async -> Bool
        private let onRecordStart: @MainActor () async throws -> String
        private let onRecordStop: @MainActor () -> String?

        init(
            onImport: @escaping @MainActor () async -> Bool,
            onRecordStart: @escaping @MainActor () async throws -> String,
            onRecordStop: @escaping @MainActor () -> String?
        ) {
            self.onImport = onImport
            self.onRecordStart = onRecordStart
            self.onRecordStop = onRecordStop
        }

        func userContentController(
            _ userContentController: WKUserContentController,
            didReceive message: WKScriptMessage
        ) {
            guard
                message.name == "duck",
                let body = message.body as? [String: Any],
                let type = body["type"] as? String
            else { return }

            if type == "import" {
                Task { @MainActor [weak self] in
                    guard let self else { return }
                    let imported = await self.onImport()
                    if imported {
                        self.webView?.reload()
                    }
                }
                return
            }

            if type == "recordStart" {
                Task { @MainActor [weak self] in
                    guard let self else { return }
                    do {
                        let path = try await self.onRecordStart()
                        self.callJS("window.duckRecordingStarted", path)
                    } catch {
                        self.callJS("window.duckRecordingError", error.localizedDescription)
                    }
                }
                return
            }

            if type == "recordStop" {
                let path = onRecordStop() ?? ""
                callJS("window.duckRecordingStopped", path)
            }
        }

        private func callJS(_ function: String, _ value: String) {
            guard let data = try? JSONSerialization.data(withJSONObject: [value]),
                  let json = String(data: data, encoding: .utf8) else { return }
            webView?.evaluateJavaScript("\(function)(\(json)[0])")
        }

        func webView(
            _ webView: WKWebView,
            decidePolicyFor navigationAction: WKNavigationAction
        ) async -> WKNavigationActionPolicy {
            guard let url = navigationAction.request.url else {
                return .cancel
            }
            if url.scheme == "http", url.host == "127.0.0.1" {
                return .allow
            }
            if url.scheme == "https" || url.scheme == "x-apple.systempreferences" {
                NSWorkspace.shared.open(url)
            }
            return .cancel
        }
    }
}
