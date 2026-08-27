import CongressTraderCore
import SwiftUI

@MainActor
final class ReportStore: ObservableObject {
    enum Phase: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    @Published private(set) var report: Report?
    @Published private(set) var phase: Phase = .idle

    private let client: EngineClient

    init(client: EngineClient = EngineClient()) {
        self.client = client
    }

    var isLoading: Bool {
        phase == .loading
    }

    func load(options: ReportOptions, pythonPath: String) async {
        phase = .loading
        do {
            report = try await client.fetch(
                options: options,
                pythonPath: pythonPath.isEmpty ? nil : pythonPath
            )
            phase = .loaded
        } catch {
            report = nil
            phase = .failed(error.localizedDescription)
        }
    }
}
