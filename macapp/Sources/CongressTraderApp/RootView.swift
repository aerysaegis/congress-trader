import CongressTraderCore
import SwiftUI

enum AppSection: String, CaseIterable, Identifiable {
    case topNames
    case sectors
    case contested
    case filers

    var id: String { rawValue }

    var title: String {
        switch self {
        case .topNames: "Top Names"
        case .sectors: "Sectors"
        case .contested: "Contested"
        case .filers: "Filers"
        }
    }

    var systemImage: String {
        switch self {
        case .topNames: "chart.line.uptrend.xyaxis"
        case .sectors: "square.grid.2x2"
        case .contested: "arrow.left.arrow.right"
        case .filers: "person.2"
        }
    }
}

struct RootView: View {
    @StateObject private var store = ReportStore()
    @State private var section: AppSection? = .topNames
    @State private var selectedTicker: String?
    @State private var options = ReportOptions.sample
    @AppStorage("pythonPath") private var pythonPath = ""

    var body: some View {
        NavigationSplitView {
            List(AppSection.allCases, selection: $section) { item in
                Label(item.title, systemImage: item.systemImage)
                    .tag(item)
            }
            .navigationTitle("Congress Trader")
            .navigationSplitViewColumnWidth(min: 180, ideal: 210, max: 250)
        } content: {
            content
                .navigationTitle(section?.title ?? "Congress Trader")
                .safeAreaInset(edge: .top, spacing: 0) {
                    ControlBar(options: $options, isLoading: store.isLoading) {
                        Task { await reload() }
                    }
                }
                .safeAreaInset(edge: .bottom, spacing: 0) {
                    if let report = store.report {
                        ReportStatusBar(report: report)
                    }
                }
        } detail: {
            detail
        }
        .navigationSplitViewStyle(.balanced)
        .task {
            guard store.phase == .idle else { return }
            await reload()
        }
    }

    @ViewBuilder
    private var content: some View {
        switch store.phase {
        case .idle, .loading where store.report == nil:
            LoadingState()
        case let .failed(message):
            ErrorState(message: message) {
                Task { await reload() }
            }
        default:
            if let report = store.report {
                switch section ?? .topNames {
                case .topNames:
                    TopNamesView(signals: report.signals, selection: $selectedTicker)
                case .sectors:
                    SectorsView(sectors: report.sectors)
                case .contested:
                    ContestedView(rows: report.contested)
                case .filers:
                    FilersView(filers: report.filers)
                }
            } else {
                EmptyState(
                    title: "No report",
                    systemImage: "doc.text.magnifyingglass",
                    message: "The engine returned no report data."
                )
            }
        }
    }

    @ViewBuilder
    private var detail: some View {
        if section == .topNames,
           let ticker = selectedTicker,
           let signal = store.report?.signals.first(where: { $0.ticker == ticker }) {
            SignalDetailView(signal: signal)
        } else {
            EmptyState(
                title: section == .topNames ? "Select a name" : section?.title ?? "Congress Trader",
                systemImage: section?.systemImage ?? "chart.line.uptrend.xyaxis",
                message: section == .topNames
                    ? "Choose a ticker to inspect its score and members."
                    : "Report details appear in the center pane."
            )
        }
    }

    private func reload() async {
        selectedTicker = nil
        await store.load(options: options, pythonPath: pythonPath)
        selectedTicker = store.report?.signals.first?.ticker
    }
}

private struct ControlBar: View {
    @Binding var options: ReportOptions
    let isLoading: Bool
    let reload: () -> Void

    var body: some View {
        HStack(spacing: 18) {
            HStack(spacing: 6) {
                Text("Source")
                    .foregroundStyle(.secondary)
                Picker("Source", selection: $options.source) {
                    ForEach(ReportSource.allCases) { source in
                        Text(source.title).tag(source)
                    }
                }
                .labelsHidden()
                .frame(width: 110)
            }

            HStack(spacing: 6) {
                Text("Lookback")
                    .foregroundStyle(.secondary)
                Stepper(value: $options.lookback, in: 1...365) {
                    Text("\(options.lookback)d")
                        .monospacedDigit()
                        .frame(width: 38, alignment: .trailing)
                }
            }

            HStack(spacing: 6) {
                Text("Members")
                    .foregroundStyle(.secondary)
                Stepper(value: $options.minMembers, in: 1...30) {
                    Text("\(options.minMembers)")
                        .monospacedDigit()
                        .frame(width: 18, alignment: .trailing)
                }
            }

            Picker("Midpoint", selection: $options.midpoint) {
                ForEach(Midpoint.allCases) { midpoint in
                    Text(midpoint.title).tag(midpoint)
                }
            }
            .pickerStyle(.segmented)
            .frame(width: 190)

            Spacer(minLength: 0)

            Button(action: reload) {
                if isLoading {
                    ProgressView()
                        .controlSize(.small)
                        .frame(width: 16, height: 16)
                } else {
                    Image(systemName: "arrow.clockwise")
                }
            }
            .buttonStyle(.borderless)
            .disabled(isLoading)
            .help("Refresh report")
            .accessibilityLabel("Refresh report")
        }
        .controlSize(.small)
        .padding(.horizontal, 14)
        .frame(height: 46)
        .background(.bar)
        .overlay(alignment: .bottom) { Divider() }
    }
}

private struct ReportStatusBar: View {
    let report: Report

    var body: some View {
        HStack(spacing: 10) {
            Text(report.source.capitalized)
            Divider().frame(height: 12)
            Text("As of \(report.asof)")
            Divider().frame(height: 12)
            Text("\(report.nTradesConsidered) trades")
            Spacer()
            if !report.hasParties {
                Label("Party data unavailable", systemImage: "person.crop.circle.badge.questionmark")
            }
        }
        .font(.caption)
        .foregroundStyle(.secondary)
        .padding(.horizontal, 12)
        .frame(height: 28)
        .background(.bar)
        .overlay(alignment: .top) { Divider() }
    }
}

private struct LoadingState: View {
    var body: some View {
        VStack(spacing: 12) {
            ProgressView()
                .controlSize(.large)
            Text("Loading report")
                .font(.headline)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

private struct ErrorState: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 30))
                .foregroundStyle(.orange)
            Text("Report unavailable")
                .font(.title3.bold())
            Text(message)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .textSelection(.enabled)
                .frame(maxWidth: 520)
            Button(action: retry) {
                Label("Try Again", systemImage: "arrow.clockwise")
            }
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct EmptyState: View {
    let title: String
    let systemImage: String
    let message: String

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: systemImage)
                .font(.system(size: 30))
                .foregroundStyle(.secondary)
            Text(title)
                .font(.title3.bold())
            Text(message)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 420)
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
