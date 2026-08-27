import Foundation

public struct Report: Codable, Sendable {
    public static let supportedSchemaVersion = 1

    public let schemaVersion: Int
    public let generatedAt: String
    public let asof: String
    public let lookback: Int
    public let minMembers: Int
    public let midpoint: String
    public let source: String
    public let hasParties: Bool
    public let nTradesConsidered: Int
    public let dropped: [String: Int]
    public let signals: [TickerSignal]
    public let sectors: [SectorRow]
    public let contested: [ContestedRow]
    public let filers: [FilerRow]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case generatedAt = "generated_at"
        case asof
        case lookback
        case minMembers = "min_members"
        case midpoint
        case source
        case hasParties = "has_parties"
        case nTradesConsidered = "n_trades_considered"
        case dropped
        case signals
        case sectors
        case contested
        case filers
    }

    public static func decode(_ data: Data) throws -> Report {
        let decoder = JSONDecoder()
        let envelope = try decoder.decode(SchemaEnvelope.self, from: data)
        guard envelope.schemaVersion == supportedSchemaVersion else {
            throw ReportSchemaError.unsupported(
                found: envelope.schemaVersion,
                supported: supportedSchemaVersion
            )
        }
        return try decoder.decode(Report.self, from: data)
    }
}

private struct SchemaEnvelope: Decodable {
    let schemaVersion: Int

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
    }
}

public enum ReportSchemaError: LocalizedError, Sendable {
    case unsupported(found: Int, supported: Int)

    public var errorDescription: String? {
        switch self {
        case let .unsupported(found, supported) where found > supported:
            return "The engine is newer than this app (schema \(found); supported \(supported)). Update Congress Trader."
        case let .unsupported(found, supported):
            return "The engine schema \(found) is incompatible with this app (supported \(supported))."
        }
    }
}

public struct TickerSignal: Codable, Identifiable, Sendable {
    public var id: String { ticker }

    public let ticker: String
    public let sector: String
    public let score: Double
    public let components: [String: Double]
    public let raw: [String: Double]
    public let nMembers: Int
    public let nBuyers: Int
    public let nSellers: Int
    public let netDollars: Double
    public let grossDollars: Double
    public let nTrades: Int
    public let buyers: [String]
    public let sellers: [String]
    public let parties: [String: Int]
    public let firstDate: String?
    public let lastDate: String?
    public let medianLagDays: Double?
    public let contested: Bool
    public let direction: String

    enum CodingKeys: String, CodingKey {
        case ticker
        case sector
        case score
        case components
        case raw
        case nMembers = "n_members"
        case nBuyers = "n_buyers"
        case nSellers = "n_sellers"
        case netDollars = "net_dollars"
        case grossDollars = "gross_dollars"
        case nTrades = "n_trades"
        case buyers
        case sellers
        case parties
        case firstDate = "first_date"
        case lastDate = "last_date"
        case medianLagDays = "median_lag_days"
        case contested
        case direction
    }
}

public struct SectorRow: Codable, Identifiable, Sendable {
    public var id: String { sector }

    public let sector: String
    public let netDollars: Double
    public let grossDollars: Double
    public let nMembers: Int
    public let nTrades: Int
    public let recentNet: Double
    public let priorNet: Double
    public let momentum: Double

    enum CodingKeys: String, CodingKey {
        case sector
        case netDollars = "net_dollars"
        case grossDollars = "gross_dollars"
        case nMembers = "n_members"
        case nTrades = "n_trades"
        case recentNet = "recent_net"
        case priorNet = "prior_net"
        case momentum
    }
}

public struct ContestedRow: Codable, Identifiable, Sendable {
    public var id: String { ticker }

    public let ticker: String
    public let sector: String
    public let buyers: [String]
    public let sellers: [String]
    public let buyDollars: Double
    public let sellDollars: Double
    public let disagreement: Double

    enum CodingKeys: String, CodingKey {
        case ticker
        case sector
        case buyers
        case sellers
        case buyDollars = "buy_dollars"
        case sellDollars = "sell_dollars"
        case disagreement
    }
}

public struct FilerRow: Codable, Identifiable, Sendable {
    public var id: String { "\(chamber):\(member)" }

    public let member: String
    public let chamber: String
    public let party: String?
    public let nTrades: Int
    public let nTickers: Int
    public let medianLagDays: Double?
    public let meanLagDays: Double?
    public let fastestLagDays: Int?
    public let grossDollars: Double

    enum CodingKeys: String, CodingKey {
        case member
        case chamber
        case party
        case nTrades = "n_trades"
        case nTickers = "n_tickers"
        case medianLagDays = "median_lag_days"
        case meanLagDays = "mean_lag_days"
        case fastestLagDays = "fastest_lag_days"
        case grossDollars = "gross_dollars"
    }
}
