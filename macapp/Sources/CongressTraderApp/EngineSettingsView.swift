import SwiftUI

struct EngineSettingsView: View {
    @AppStorage("pythonPath") private var pythonPath = ""

    var body: some View {
        Form {
            TextField("Python interpreter", text: $pythonPath)
                .textFieldStyle(.roundedBorder)

            HStack {
                Spacer()
                Button {
                    pythonPath = ""
                } label: {
                    Label("Use Auto-detect", systemImage: "location.magnifyingglass")
                }
                .disabled(pythonPath.isEmpty)
            }
        }
        .padding(20)
        .frame(width: 520)
    }
}
