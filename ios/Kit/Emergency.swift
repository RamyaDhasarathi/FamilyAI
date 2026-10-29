// The emergency card and safe check-ins (familyos/emergency.py). The card is what a sitter, a school or a first responder needs: contacts, who may
// collect each child, allergies and current medicines, critical documents, and (only if asked for) how to get into the home.
import Foundation

public struct EmergencyPerson: Codable, Hashable {
    public let name: String
    public let role: String
    public let allergies: String?
    public let bloodGroup: String?
    public let medicines: [String]
}
public struct EmergencyContact: Codable, Hashable { public let name: String; public let relation: String?; public let phone: String? }
public struct EmergencyPickup: Codable, Hashable { public let child: String; public let name: String; public let relation: String?; public let phone: String? }
public struct EmergencyDocument: Codable, Hashable {
    public let kind: String
    public let holder: String?
    public let issuer: String?
    public let identifierTail: String?
    public let expiresOn: Date?
}
public struct EmergencyCard: Codable {
    public let household: String?
    public let people: [EmergencyPerson]
    public let contacts: [EmergencyContact]
    public let pickup: [EmergencyPickup]
    public let documents: [EmergencyDocument]
    public let homeAccess: String?
}
public struct EmergencyCheckin: Codable, Identifiable, Hashable {
    public var id: String { name }
    public let name: String
    public let status: String
    public let note: String?
    public let at: Date
}
public struct EmergencyShare: Codable, Identifiable, Hashable {
    public let id: UUID
    public let label: String
    public let includeHome: Bool
    public let expiresAt: Date
    public let openedCount: Int?
    public let active: Bool?
}
/// Shown once, when the link is made.
public struct EmergencyShareMade: Codable { public let id: UUID; public let token: String; public let path: String; public let expiresAt: Date; public let label: String }

private struct CheckinBody: Encodable { let status: String; let note: String? }
private struct ShareBody: Encodable { let label: String; let hours: Int; let includeHome: Bool }

extension API {
    public func emergencyCard() async throws -> EmergencyCard { try await json("GET", "/emergency/card") }
    public func emergencyCheckins() async throws -> [EmergencyCheckin] { try await json("GET", "/emergency/checkins") }
    public func emergencyCheckin(safe: Bool, note: String? = nil) async throws {
        struct Ignored: Decodable {}
        let _: Ignored = try await json("POST", "/emergency/checkin", body: CheckinBody(status: safe ? "safe" : "need_help", note: note))
    }
    public func emergencyShares() async throws -> [EmergencyShare] { try await json("GET", "/emergency/shares") }
    public func shareEmergency(label: String, hours: Int, includeHome: Bool) async throws -> EmergencyShareMade {
        try await json("POST", "/emergency/share", body: ShareBody(label: label, hours: hours, includeHome: includeHome))
    }
    public func revokeEmergencyShare(_ id: UUID) async throws { _ = try await send("DELETE", "/emergency/shares/\(id.uuidString)") }
}
