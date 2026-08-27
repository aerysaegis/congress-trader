import CongressTraderCore
import SwiftUI

struct SectorsView: View {
    let sectors: [SectorRow]

    var body: some View {
        if sectors.isEmpty {
            EmptyState(
                title: "No sector activity",
                systemImage: "square.grid.2x2",
                message: "No sector rows were available for this report."
            )
        } else {
            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(sectors) { sector in
                        SectorRowView(sector: sector, scale: scale)
                        Divider()
                    }
                }
            }
        }
    }

    private var scale: Double {
        max(sectors.map { abs($0.momentum) }.max() ?? 1, 0.01)
    }
}

private struct SectorRowView: View {
    let sector: SectorRow
    let scale: Double

    var body: some View {
        HStack(spacing: 18) {
            VStack(alignment: .leading, spacing: 3) {
                Text(sector.sector)
                    .fontWeight(.semibold)
                Text("\(sector.nMembers) members  \(sector.nTrades) trades")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .frame(width: 190, alignment: .leading)

            MomentumBar(value: sector.momentum, scale: scale)
                .frame(minWidth: 220, maxWidth: .infinity)

            DirectionalValue(value: sector.momentum)
                .frame(width: 88, alignment: .trailing)

            VStack(alignment: .trailing, spacing: 3) {
                Text(Money.compact(sector.netDollars))
                    .monospacedDigit()
                Text("net flow")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .frame(width: 86, alignment: .trailing)
        }
        .padding(.horizontal, 16)
        .frame(height: 64)
    }
}

private struct MomentumBar: View {
    let value: Double
    let scale: Double

    var body: some View {
        GeometryReader { proxy in
            let width = proxy.size.width
            let half = width / 2
            let extent = min(abs(value) / scale, 1) * half

            ZStack {
                Rectangle()
                    .fill(.quaternary)
                    .frame(height: 8)
                Rectangle()
                    .fill(value >= 0 ? Color.green : Color.red)
                    .frame(width: extent, height: 8)
                    .offset(x: value >= 0 ? extent / 2 : -extent / 2)
                Rectangle()
                    .fill(.secondary)
                    .frame(width: 1, height: 16)
            }
            .frame(width: width, height: proxy.size.height)
        }
        .frame(height: 18)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Momentum \(String(format: "%+.2f", value))")
    }
}
