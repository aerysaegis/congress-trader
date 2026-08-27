import CongressTraderCore
import SwiftUI

struct FilersView: View {
    let filers: [FilerRow]
    @State private var sortOrder = [
        KeyPathComparator(\FilerRow.sortableMedianLag),
    ]

    var body: some View {
        if filers.isEmpty {
            EmptyState(
                title: "No filer data",
                systemImage: "person.2",
                message: "No disclosure timing data was available for this report."
            )
        } else {
            Table(filers.sorted(using: sortOrder), sortOrder: $sortOrder) {
                TableColumn("Member", value: \.member)
                    .width(min: 150, ideal: 210)
                TableColumn("Chamber", value: \.chamber) { filer in
                    Text(filer.chamber.capitalized)
                }
                .width(min: 68, ideal: 80)
                TableColumn("Party", value: \.sortableParty) { filer in
                    Text(filer.party ?? "-")
                }
                .width(min: 42, ideal: 50)
                TableColumn("Trades", value: \.nTrades) { filer in
                    Text("\(filer.nTrades)").monospacedDigit()
                }
                .width(min: 52, ideal: 60)
                TableColumn("Tickers", value: \.nTickers) { filer in
                    Text("\(filer.nTickers)").monospacedDigit()
                }
                .width(min: 52, ideal: 60)
                TableColumn("Median lag", value: \.sortableMedianLag) { filer in
                    Text(filer.medianLagDays.map { String(format: "%.1fd", $0) } ?? "-")
                        .monospacedDigit()
                }
                .width(min: 76, ideal: 86)
                TableColumn("Fastest", value: \.sortableFastestLag) { filer in
                    Text(filer.fastestLagDays.map { "\($0)d" } ?? "-")
                        .monospacedDigit()
                }
                .width(min: 62, ideal: 70)
                TableColumn("Gross $", value: \.grossDollars) { filer in
                    Text(Money.compact(filer.grossDollars))
                        .monospacedDigit()
                }
                .width(min: 78, ideal: 92)
            }
        }
    }
}

private extension FilerRow {
    var sortableParty: String { party ?? "" }
    var sortableMedianLag: Double { medianLagDays ?? .greatestFiniteMagnitude }
    var sortableFastestLag: Int { fastestLagDays ?? .max }
}
