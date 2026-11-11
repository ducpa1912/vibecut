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
                    onImport: { mode, projectID in
                        await model.importVideo(mode: mode, projectID: projectID)
                    },
                    onImportNotice: { model.notice },
                    onDropFiles: { url, projectID in
                        await model.importVideo(
                            at: url,
                            mode: projectID.isEmpty ? "new" : "scenes",
                            projectID: projectID.isEmpty ? nil : projectID
                        )
                    },
                    onRecordStart: { try await model.startRecording() },
                    onRecordStop: { model.stopRecording() },
                    onChooseModelFolder: { await model.chooseModelFolder() }
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
        .ignoresSafeArea(.container, edges: .top)
        .task { await model.start() }
        .onAppear { Task { await model.start() } }
        .onDisappear { model.stop() }
    }
}

private struct WebView: NSViewRepresentable {
    let url: URL
    let onImport: @MainActor (String, String?) async -> Bool
    let onImportNotice: @MainActor () -> String?
    let onDropFiles: @MainActor (URL, String) async -> Bool
    let onRecordStart: @MainActor () async throws -> String
    let onRecordStop: @MainActor () -> String?
    let onChooseModelFolder: @MainActor () async -> (path: String?, error: String?)

    func makeNSView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true
        configuration.websiteDataStore = .nonPersistent()

        let controller = WKUserContentController()
        controller.add(context.coordinator, name: "duck")
        configuration.userContentController = controller

        let view = DropWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = context.coordinator
        view.underPageBackgroundColor = .clear
        view.onFiles = { urls in
            guard let first = urls.first else { return }
            view.evaluateJavaScript("window.duckProjectId ? window.duckProjectId() : ''") { value, _ in
                let projectID = (value as? String) ?? ""
                Task { @MainActor in
                    let imported = await onDropFiles(first, projectID)
                    if imported {
                        view.reload()
                    } else if let message = onImportNotice(), !message.isEmpty {
                        context.coordinator.callJS("window.duckImportError", message)
                    }
                }
            }
        }
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
            onImportNotice: onImportNotice,
            onDropFiles: onDropFiles,
            onRecordStart: onRecordStart,
            onRecordStop: onRecordStop,
            onChooseModelFolder: onChooseModelFolder
        )
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        weak var webView: WKWebView?
        private let onImport: @MainActor (String, String?) async -> Bool
        private let onImportNotice: @MainActor () -> String?
        private let onDropFiles: @MainActor (URL, String) async -> Bool
        private let onRecordStart: @MainActor () async throws -> String
        private let onRecordStop: @MainActor () -> String?
        private let onChooseModelFolder: @MainActor () async -> (path: String?, error: String?)
        nonisolated(unsafe) private var mouseDownEvent: NSEvent?
        nonisolated(unsafe) private var mouseMonitor: Any?

        init(
            onImport: @escaping @MainActor (String, String?) async -> Bool,
            onImportNotice: @escaping @MainActor () -> String?,
            onDropFiles: @escaping @MainActor (URL, String) async -> Bool,
            onRecordStart: @escaping @MainActor () async throws -> String,
            onRecordStop: @escaping @MainActor () -> String?,
            onChooseModelFolder: @escaping @MainActor () async -> (path: String?, error: String?)
        ) {
            self.onImport = onImport
            self.onImportNotice = onImportNotice
            self.onDropFiles = onDropFiles
            self.onRecordStart = onRecordStart
            self.onRecordStop = onRecordStop
            self.onChooseModelFolder = onChooseModelFolder
            super.init()
            mouseMonitor = NSEvent.addLocalMonitorForEvents(matching: [.leftMouseDown]) { [weak self] event in
                self?.mouseDownEvent = event
                return event
            }
        }

        deinit {
            if let mouseMonitor {
                NSEvent.removeMonitor(mouseMonitor)
            }
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
                let mode = (body["mode"] as? String) ?? "new"
                let projectID = (body["projectId"] as? String).flatMap {
                    $0.isEmpty ? nil : $0
                }
                Task { @MainActor [weak self] in
                    guard let self else { return }
                    let imported = await self.onImport(mode, projectID)
                    if imported {
                        self.webView?.reload()
                    } else if let message = self.onImportNotice(), !message.isEmpty {
                        self.callJS("window.duckImportError", message)
                    }
                }
                return
            }

            if type == "windowDrag" {
                if let event = mouseDownEvent {
                    webView?.window?.performDrag(with: event)
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

            if type == "chooseModelFolder" {
                Task { @MainActor [weak self] in
                    guard let self else { return }
                    let result = await self.onChooseModelFolder()
                    if let path = result.path {
                        self.callJS("window.duckModelFolder", path)
                    } else if let error = result.error {
                        self.callJS("window.duckModelFolderError", error)
                    }
                }
                return
            }
        }

        func callJS(_ function: String, _ value: String) {
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


private final class DropWebView: WKWebView {
    var onFiles: (([URL]) -> Void)?

    override init(frame: CGRect, configuration: WKWebViewConfiguration) {
        super.init(frame: frame, configuration: configuration)
        registerForDraggedTypes([.fileURL])
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        registerForDraggedTypes([.fileURL])
    }

    private func videoURLs(_ info: NSDraggingInfo) -> [URL] {
        let options: [NSPasteboard.ReadingOptionKey: Any] = [
            .urlReadingFileURLsOnly: true,
        ]
        let urls = info.draggingPasteboard.readObjects(
            forClasses: [NSURL.self], options: options
        ) as? [URL] ?? []
        return urls.filter {
            ["mp4", "mov", "m4v"].contains($0.pathExtension.lowercased())
        }
    }

    override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
        videoURLs(sender).isEmpty ? [] : .copy
    }

    override func draggingUpdated(_ sender: NSDraggingInfo) -> NSDragOperation {
        videoURLs(sender).isEmpty ? [] : .copy
    }

    override func prepareForDragOperation(_ sender: NSDraggingInfo) -> Bool {
        !videoURLs(sender).isEmpty
    }

    override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        let urls = videoURLs(sender)
        guard !urls.isEmpty else { return false }
        onFiles?(urls)
        return true
    }
}
