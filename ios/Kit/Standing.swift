// Payments the household owes on a rhythm no notice announces, and the accounts it tracks so a bill that never arrives is noticed
// (familyos/standing.py, billers.py). FamilyOS reminds; it never pays. Nothing here moves money.
import Foundation

public struct StandingPayment: Codable, Identifiable, Hashable {
    public let id: UUID
    public let title: String
    public let payee: String
    public let amount: Double
    public let currency: String
    public let dayOfMonth: Int
    public let nextDue: Date
    public let subjectName: String?
    public let visibility: String
    public let createdBy: UUID
}

public struct Biller: Codable, Identifiable, Hashable {
    public let id: UUID
    public let label: String
    public let provider: String
    public let identifierHint: String?
    public let everyDays: Int
    public let graceDays: Int
    public let visibility: String
    public let lastSeenAt: Date?
}

/// An obligation whose action is a payment.
public struct BillDue: Codable, Identifiable, Hashable {
    public let id: UUID
    public let title: String
    public let dueDate: Date?
    public let status: String
}

private struct NewStanding: Encodable {
    let title: String
    let payee: String
    let amount: Double
    let dayOfMonth: Int
    let visibility: String
}

private struct NewBiller: Encodable {
    let label: String
    let provider: String
    let identifier: String?
    let everyDays: Int
    let visibility: String
}

extension API {
    public func standingPayments() async throws -> [StandingPayment] { try await json("GET", "/standing") }
    public func addStanding(title: String, payee: String, amount: Double, day: Int, shared: Bool) async throws -> StandingPayment {
        try await json("POST", "/standing", body: NewStanding(title: title, payee: payee, amount: amount, dayOfMonth: day, visibility: shared ? "shared" : "private"))
    }
    public func stopStanding(_ id: UUID) async throws { _ = try await send("DELETE", "/standing/\(id.uuidString)") }

    public func billers() async throws -> [Biller] { try await json("GET", "/billers") }
    public func addBiller(label: String, provider: String, number: String?, everyDays: Int, shared: Bool) async throws -> Biller {
        try await json("POST", "/billers", body: NewBiller(label: label, provider: provider, identifier: number, everyDays: everyDays, visibility: shared ? "shared" : "private"))
    }
    public func forgetBiller(_ id: UUID) async throws { _ = try await send("DELETE", "/billers/\(id.uuidString)") }

    public func billsDue() async throws -> [BillDue] { try await json("GET", "/bills") }
}
