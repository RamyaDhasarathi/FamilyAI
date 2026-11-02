// Returns and warranties (familyos/finance.py): a purchase with how long it
// can go back and how long it is covered. The server works out the dates.
import Foundation

public struct Warranty: Codable, Identifiable, Hashable {
    public let id: UUID
    public let title: String
    public let merchant: String?
    public let purchasedOn: Date?
    public let returnBy: Date?
    public let warrantyUntil: Date?
    public let artifactId: UUID?
}

struct WarrantyBody: Encodable {
    let title: String
    let merchant: String?
    let purchasedOn: Date?
    let returnDays: Int?
    let warrantyMonths: Int?
    let artifactId: UUID?
}

extension API {
    /// Purchases with a return window or a warranty still running, soonest first.
    public func warranties() async throws -> [Warranty] { try await json("GET", "/finance/warranties") }
    public func addWarranty(title: String, merchant: String?, purchasedOn: Date?, returnDays: Int?, warrantyMonths: Int?, artifactId: UUID? = nil) async throws -> Warranty {
        try await json("POST", "/finance/warranties", body: WarrantyBody(title: title, merchant: merchant, purchasedOn: purchasedOn,
                                                                          returnDays: returnDays, warrantyMonths: warrantyMonths, artifactId: artifactId))
    }
    /// Closed: returned, claimed, or no longer worth watching. It leaves the list.
    public func closeWarranty(_ id: UUID) async throws { _ = try await send("DELETE", "/finance/warranties/\(id.uuidString)") }
}
