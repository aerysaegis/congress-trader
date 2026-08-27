import Foundation

enum Money {
    static func compact(_ value: Double) -> String {
        let absolute = abs(value)
        let sign = value < 0 ? "-" : ""
        if absolute >= 1_000_000 {
            return "\(sign)$\(String(format: "%.1f", absolute / 1_000_000))M"
        }
        if absolute >= 1_000 {
            return "\(sign)$\(String(format: "%.0f", absolute / 1_000))k"
        }
        return "\(sign)$\(String(format: "%.0f", absolute))"
    }

    static func full(_ value: Double) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.maximumFractionDigits = 0
        return formatter.string(from: NSNumber(value: value)) ?? compact(value)
    }
}
