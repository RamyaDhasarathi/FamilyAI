// Who has been handed what, and the named scopes a guardian hands out (familyos/grants.py, circle.py). A grant reaches obligations only, never the
// notices they were read from, and ends by itself. Anyone may read the list: who can see what about you is yours to know.
import Foundation

public struct HouseholdGrant: Codable, Identifiable, Hashable {
    public let id: UUID
    public let granteeMemberId: UUID
    public let granteeName: String
    public let grantedByName: String
    public let subjectName: String?
    public let actions: [String]
    public let reason: String
    public let expiresAt: Date
}

public struct CirclePreset: Codable, Identifiable, Hashable {
    public let key: String
    public let label: String
    public let actions: [String]
    public let days: Int
    public let needsChild: Bool?
    public var id: String { key }
}

private struct PresetBody: Encodable {
    let memberId: UUID
    let subjectMemberId: UUID?
    let days: Int?
}

public struct Revoked: Codable { public let revoked: String }

extension API {
    public func grants() async throws -> [HouseholdGrant] { try await json("GET", "/grants") }
    public func circlePresets() async throws -> [CirclePreset] { try await json("GET", "/circle/presets") }
    public func grantPreset(_ key: String, to member: UUID, about child: UUID?, days: Int?) async throws -> HouseholdGrant {
        try await json("POST", "/circle/presets/\(key)", body: PresetBody(memberId: member, subjectMemberId: child, days: days))
    }
    public func revokeGrant(_ id: UUID) async throws { let _: Revoked = try await json("DELETE", "/grants/\(id.uuidString)") }
}
