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
                WebView(url: url) {
                    await model.importVideo()
                }
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
        .onDisappear { model.stop() }
    }
}

private struct WebView: NSViewRepresentable {
    let url: URL
    let onImport: @MainActor () async -> Bool

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
        Coordinator(onImport: onImport)
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        weak var webView: WKWebView?
        private let onImport: @MainActor () async -> Bool

        init(onImport: @escaping @MainActor () async -> Bool) {
            self.onImport = onImport
        }

        func userContentController(
            _ userContentController: WKUserContentController,
            didReceive message: WKScriptMessage
        ) {
            guard
                message.name == "duck",
                let body = message.body as? [String: Any],
                body["type"] as? String == "import"
            else { return }

            Task { @MainActor [weak self] in
                guard let self else { return }
                let imported = await self.onImport()
                if imported {
                    self.webView?.reload()
                }
            }
        }

        func webView(
            _ webView: WKWebView,
            decidePolicyFor navigationAction: WKNavigationAction,
            decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
        ) {
            guard let url = navigationAction.request.url else {
                decisionHandler(.cancel)
                return
            }
            if url.scheme == "http", url.host == "127.0.0.1" {
                decisionHandler(.allow)
                return
            }
            if url.scheme == "https" {
                NSWorkspace.shared.open(url)
            }
            decisionHandler(.cancel)
        }
    }
}
