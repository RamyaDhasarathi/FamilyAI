// Consent for a child's records, the weekly digest, what-if scenarios and notices that did not arrive (familyos/consent.py, digest.py, scenarios.py,
// gaps.py). A scenario changes nothing and proposes nothing. Withdrawing a consent erases what names the child, so the screen says so first.
import Foundation

public struct ChildConsent: Codable, Identifiable, Hashable {
    public let id: UUID
    public let subjectMemberId: UUID
    public let purpose: String
    public let noticeVersion: String
    public let verificationMethod: String
    public let guardianDeclaredAt: Date?
    public let grantedAt: Date
    public let withdrawnAt: Date?
    public var isActive: Bool { withdrawnAt == nil }
}

public struct ErasureStarted: Codable {
    public let id: UUID
    public let scope: String
    public let status: String
}

private struct NewConsent: Encodable {
    let subjectMemberId: UUID
    let purpose = "household_records"
    let noticeVersion: String
    let verificationMethod = "account_holder"
    let declaresGuardian: Bool
}

public struct DigestPreview: Codable {
    public let subject: String
    public let body: String
    public let sendsOn: String
}

public struct DigestSent: Codable {
    public let sent: Bool
    public let channel: String?
    public let why: String?
}

public struct ScenarioImpact: Codable, Hashable {
    public let kind: String
    public let title: String
    public let date: Date?
    public let note: String?
    public let cover: [String]?
}

public struct ScenarioResult: Codable {
    public let scenario: String
    public let headline: String
    public let impacts: [ScenarioImpact]
    public let changesNothing: Bool
}

public struct ScenarioRequest: Encodable {
    public enum Kind: String, Encodable { case memberAway = "member_away", spend, schoolReopens = "school_reopens" }
    public var kind: Kind
    public var memberId: UUID?
    public var start: Date?
    public var end: Date?
    public var amount: Double?
    public var reopensOn: Date?
    public init(kind: Kind) { self.kind = kind }
}

public struct IntakeGap: Codable, Identifiable, Hashable {
    public let id: UUID
    public let title: String
    public let livedWhere: String
    public let alsoEmailed: Bool?
    public let hadDate: Bool
    public let arrivedAs: UUID?
    public let createdAt: Date
}

public struct GapWhere: Codable, Hashable {
    public let livedWhere: String
    public let count: Int
    public let means: String
}

public struct CaptureSummary: Codable {
    public let captured: Int
    public let missedReported: Int
    public let captureRate: Double?
    public let missedByWhere: [GapWhere]
    public let caveat: String
}

private struct NewGap: Encodable {
    let title: String
    let livedWhere: String
    let alsoEmailed: Bool?
    let hadDate: Bool
}

extension API {
    public func consents() async throws -> [ChildConsent] { try await json("GET", "/consents") }
    public func grantConsent(for child: UUID, notice: String, declared: Bool) async throws -> ChildConsent {
        try await json("POST", "/consents", body: NewConsent(subjectMemberId: child, noticeVersion: notice, declaresGuardian: declared))
    }
    public func withdrawConsent(_ id: UUID) async throws -> ErasureStarted { try await json("POST", "/consents/\(id.uuidString)/withdraw") }

    public func digestPreview() async throws -> DigestPreview { try await json("GET", "/digest") }
    public func sendDigest() async throws -> DigestSent { try await json("POST", "/digest/send") }

    public func runScenario(_ request: ScenarioRequest) async throws -> ScenarioResult { try await json("POST", "/scenarios", body: request) }

    public func intakeGaps() async throws -> [IntakeGap] { try await json("GET", "/intake-gaps") }
    public func captureSummary() async throws -> CaptureSummary { try await json("GET", "/intake-gaps/summary") }
    public func reportGap(title: String, livedWhere: String, alsoEmailed: Bool?, hadDate: Bool) async throws -> IntakeGap {
        try await json("POST", "/intake-gaps", body: NewGap(title: title, livedWhere: livedWhere, alsoEmailed: alsoEmailed, hadDate: hadDate))
    }
}
