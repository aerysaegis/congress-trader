import CongressTraderCore
import SwiftUI

struct ContestedView: View {
    let rows: [ContestedRow]

    var body: some View {
        if rows.isEmpty {
            EmptyState(
                title: "No contested names",
                systemImage: "arrow.left.arrow.right",
                message: "No ticker had members trading on both sides."
            )
        } else {
            List(rows) { row in
                VStack(alignment: .leading, spacing: 8) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(row.ticker)
                            .font(.headline)
                        Text(row.sector)
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text("\(Int((row.disagreement * 100).rounded()))% split")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    HStack(spacing: 24) {
                        MemberSummary(
                            title: "Buyers",
                            names: row.buyers,
                            dollars: row.buyDollars,
                            systemImage: "arrow.up.right",
                            color: .green
                        )
                        MemberSummary(
                            title: "Sellers",
                            names: row.sellers,
                            dollars: row.sellDollars,
                            systemImage: "arrow.down.right",
                            color: .red
                        )
                    }
                }
                .padding(.vertical, 7)
            }
            .listStyle(.inset)
        }
    }
}

private struct MemberSummary: View {
    let title: String
    let names: [String]
    let dollars: Double
    let systemImage: String
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 5) {
                Image(systemName: systemImage)
                Text("\(title) \(names.count)")
                Text(Money.compact(dollars))
                    .monospacedDigit()
            }
            .foregroundStyle(color)
            Text(names.joined(separator: ", "))
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
