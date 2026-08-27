import SwiftUI

@main
struct CongressTraderApp: App {
    var body: some Scene {
        WindowGroup {
            RootView()
        }
        .defaultSize(width: 1_280, height: 800)

        Settings {
            EngineSettingsView()
        }
    }
}
