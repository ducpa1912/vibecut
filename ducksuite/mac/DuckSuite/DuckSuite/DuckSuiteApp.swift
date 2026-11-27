import SwiftUI

@MainActor
final class DuckSuiteAppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            self.keepWindowsOnScreen(NSApp)
        }
    }

    func applicationShouldHandleReopen(
        _ sender: NSApplication,
        hasVisibleWindows flag: Bool
    ) -> Bool {
        keepWindowsOnScreen(sender)
        if !flag {
            for window in sender.windows where window.canBecomeMain {
                window.makeKeyAndOrderFront(nil)
                sender.activate(ignoringOtherApps: true)
                return true
            }
        }
        return true
    }

    private func keepWindowsOnScreen(_ app: NSApplication) {
        guard let screen = NSScreen.screens.first ?? NSScreen.main else { return }
        let visible = screen.visibleFrame
        for window in app.windows where window.canBecomeMain {
            window.styleMask.insert(.fullSizeContentView)
            window.titlebarAppearsTransparent = true
            window.titleVisibility = .hidden
            window.titlebarSeparatorStyle = .none
            window.backgroundColor = NSColor(calibratedRed: 0.965, green: 0.941, blue: 0.91, alpha: 1)
            window.isMovableByWindowBackground = true
            var frame = window.frame
            let intersectsActiveScreen = visible.intersects(frame)
            if !intersectsActiveScreen || frame.width > visible.width || frame.height > visible.height {
                frame.size.width = min(frame.width, visible.width)
                frame.size.height = min(frame.height, visible.height)
                frame.origin.x = visible.midX - frame.width / 2
                frame.origin.y = visible.midY - frame.height / 2
            } else {
                frame.origin.x = min(max(frame.minX, visible.minX), visible.maxX - frame.width)
                frame.origin.y = min(max(frame.minY, visible.minY), visible.maxY - frame.height)
            }
            if frame != window.frame {
                window.setFrame(frame, display: true)
            }
        }
    }
}

@main
struct DuckSuiteApp: App {
    @NSApplicationDelegateAdaptor(DuckSuiteAppDelegate.self) private var appDelegate
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(model)
                .frame(minWidth: 1280, minHeight: 800)
        }
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.contentMinSize)
        .defaultSize(width: 1440, height: 900)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("New Project") {}
                    .keyboardShortcut("n", modifiers: .command)
                    .disabled(true)
            }
        }
    }
}
