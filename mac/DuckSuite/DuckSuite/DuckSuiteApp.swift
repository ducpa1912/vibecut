import SwiftUI

@main
struct DuckSuiteApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(model)
                .frame(minWidth: 1080, minHeight: 700)
        }
        .windowStyle(.titleBar)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("New Project") {}
                    .keyboardShortcut("n", modifiers: .command)
                    .disabled(true)
            }
        }
    }
}
