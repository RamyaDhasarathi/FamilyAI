// One person's papers, bills, appointments, medicines and the messages that looked wrong (familyos/circle.py, `care`), read through the caller's
// own visibility. Only what the screen shows is decoded; the server's other keys are ignored.
import Foundation

public struct CareDocument: Codable, Hashable {
    public let label: String
    public let title: String
    public let expiresOn: Date?
    public let status: String
    public let daysLeft: Int?
}

public struct CareNote: Codable, Hashable {
    public let title: String
    public let why: String?
}

public struct CareDated: Codable, Hashable {
    public let title: String
    public let dueDate: Date?
    public let status: String?
}

public struct CareMedicine: Codable, Hashable {
    public let drug: String
    public let doseText: String?
    public let timesPerDay: Int?
    public let status: String
    public let daysLeft: Int?
}

public struct CareScam: Codable, Hashable {
    public struct Suspicion: Codable, Hashable { public let level: String? }
    public let headline: String?
    public let receivedAt: Date
    public let suspicion: Suspicion?
}

public struct CareSummary: Codable {
    public let member: Member
    public let documents: [CareDocument]
    public let documentChecks: [CareNote]
    public let bills: [CareDated]
    public let appointments: [CareDated]
    public let medications: [CareMedicine]
    public let standing: [StandingPayment]
    public let unusual: [CareNote]
    public let scams: [CareScam]
    public let handedOver: [HouseholdGrant]
}

extension API {
    public func care(_ member: UUID) async throws -> CareSummary { try await json("GET", "/members/\(member.uuidString)/care") }
}
