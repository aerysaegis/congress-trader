import CongressTraderCore
import SwiftUI

struct SignalDetailView: View {
    let signal: TickerSignal

    private let componentOrder = [
        "breadth", "net_flow", "acceleration", "cluster", "freshness", "bipartisan",
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(signal.ticker)
                            .font(.largeTitle.bold())
                        Text(signal.sector)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    DirectionalValue(value: signal.score)
                        .font(.title3.bold())
                }

                Divider()

                Grid(alignment: .leading, horizontalSpacing: 24, verticalSpacing: 10) {
                    metricRow("Net flow", Money.full(signal.netDollars))
                    metricRow("Gross flow", Money.full(signal.grossDollars))
                    metricRow("Members", "\(signal.nMembers)")
                    metricRow("Trades", "\(signal.nTrades)")
                    metricRow("Median lag", signal.medianLagDays.map { String(format: "%.1f days", $0) } ?? "-")
                    metricRow("Window", dateWindow)
                }

                Divider()

                VStack(alignment: .leading, spacing: 10) {
                    Text("Score Components")
                        .font(.headline)
                    ForEach(visibleComponents, id: \.0) { name, value in
                        HStack {
                            Text(name.replacingOccurrences(of: "_", with: " ").capitalized)
                            Spacer()
                            Text(String(format: "%+.2f", value))
                                .monospacedDigit()
                                .foregroundStyle(value >= 0 ? .green : .red)
                        }
                    }
                }

                Divider()

                HStack(alignment: .top, spacing: 28) {
                    MemberList(title: "Buyers", members: signal.buyers, systemImage: "arrow.up.right")
                    MemberList(title: "Sellers", members: signal.sellers, systemImage: "arrow.down.right")
                }
            }
            .padding(22)
        }
        .navigationTitle(signal.ticker)
    }

    private var dateWindow: String {
        switch (signal.firstDate, signal.lastDate) {
        case let (first?, last?): "\(first) to \(last)"
        default: "-"
        }
    }

    private var visibleComponents: [(String, Double)] {
        componentOrder.compactMap { key in
            signal.components[key].map { (key, $0) }
        }
    }

    @ViewBuilder
    private func metricRow(_ label: String, _ value: String) -> some View {
        GridRow {
            Text(label)
                .foregroundStyle(.secondary)
            Text(value)
                .monospacedDigit()
                .textSelection(.enabled)
        }
    }
}

private struct MemberList: View {
    let title: String
    let members: [String]
    let systemImage: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("\(title)  \(members.count)", systemImage: systemImage)
                .font(.headline)
            if members.isEmpty {
                Text("None")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(members, id: \.self) { member in
                    Text(member)
                        .textSelection(.enabled)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
