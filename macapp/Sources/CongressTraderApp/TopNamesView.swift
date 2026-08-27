import CongressTraderCore
import SwiftUI

struct TopNamesView: View {
    let signals: [TickerSignal]
    @Binding var selection: String?
    @State private var sortOrder = [
        KeyPathComparator(\TickerSignal.score, order: .reverse),
    ]

    var body: some View {
        if signals.isEmpty {
            EmptyState(
                title: "No names cleared the floor",
                systemImage: "line.3.horizontal.decrease.circle",
                message: "Adjust the member floor or report window and refresh."
            )
        } else {
            Table(signals.sorted(using: sortOrder), selection: $selection, sortOrder: $sortOrder) {
                TableColumn("Ticker", value: \.ticker) { signal in
                    Text(signal.ticker)
                        .fontWeight(.semibold)
                }
                .width(min: 58, ideal: 66)

                TableColumn("Score", value: \.score) { signal in
                    DirectionalValue(value: signal.score)
                }
                .width(min: 76, ideal: 82)

                TableColumn("Members", value: \.nMembers) { signal in
                    Text("\(signal.nMembers)")
                        .monospacedDigit()
                }
                .width(min: 62, ideal: 70)

                TableColumn("Buyers", value: \.nBuyers) { signal in
                    Text("\(signal.nBuyers)")
                        .monospacedDigit()
                }
                .width(min: 54, ideal: 62)

                TableColumn("Sellers", value: \.nSellers) { signal in
                    Text("\(signal.nSellers)")
                        .monospacedDigit()
                }
                .width(min: 54, ideal: 62)

                TableColumn("Net $", value: \.netDollars) { signal in
                    Text(Money.compact(signal.netDollars))
                        .monospacedDigit()
                }
                .width(min: 78, ideal: 92)

                TableColumn("Sector", value: \.sector)
                    .width(min: 120, ideal: 170)

                TableColumn("Median lag", value: \.sortableMedianLag) { signal in
                    Text(signal.medianLagDays.map { String(format: "%.1fd", $0) } ?? "-")
                        .foregroundStyle(signal.medianLagDays == nil ? .secondary : .primary)
                        .monospacedDigit()
                }
                .width(min: 82, ideal: 92)
            }
        }
    }
}

private extension TickerSignal {
    var sortableMedianLag: Double {
        medianLagDays ?? .greatestFiniteMagnitude
    }
}

struct DirectionalValue: View {
    let value: Double

    var body: some View {
        Label {
            Text(String(format: "%+.2f", value))
                .monospacedDigit()
        } icon: {
            Image(systemName: value >= 0 ? "arrow.up.right" : "arrow.down.right")
        }
        .foregroundStyle(value >= 0 ? .green : .red)
        .accessibilityLabel(value >= 0 ? "Positive \(value)" : "Negative \(value)")
    }
}
