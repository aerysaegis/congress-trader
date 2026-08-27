import Foundation

public struct ReportOptions: Equatable, Sendable {
    public var lookback: Int
    public var minMembers: Int
    public var midpoint: Midpoint
    public var source: ReportSource

    public init(
        lookback: Int = 60,
        minMembers: Int = 3,
        midpoint: Midpoint = .geometric,
        source: ReportSource = .sample
    ) {
        self.lookback = lookback
        self.minMembers = minMembers
        self.midpoint = midpoint
        self.source = source
    }

    public static let sample = ReportOptions()

    var arguments: [String] {
        var result = [
            "-m", "congress_trader", "report", "--json",
            "--lookback", String(lookback),
            "--min-members", String(minMembers),
            "--midpoint", midpoint.rawValue,
        ]
        if source == .sample {
            result.append("--sample")
        } else {
            result.append(contentsOf: ["--source", source.rawValue])
        }
        return result
    }
}

public enum Midpoint: String, CaseIterable, Identifiable, Sendable {
    case geometric
    case arithmetic

    public var id: String { rawValue }

    public var title: String {
        rawValue.capitalized
    }
}

public enum ReportSource: String, CaseIterable, Identifiable, Sendable {
    case sample
    case live
    case house
    case senate

    public var id: String { rawValue }

    public var title: String {
        rawValue.capitalized
    }
}
