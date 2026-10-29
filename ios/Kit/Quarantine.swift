// Mail and shares held because FamilyOS does not know the sender (familyos/artifacts.py). A guardian looks at what came and says whose it is, or
// turns it away. Accepting also vouches for the sender, so the next one from there is read rather than held.
import Foundation

public struct HeldSource: Codable, Hashable {
    public let from: String?
    public let fromName: String?
    public let subject: String?
}

public struct HeldItem: Codable, Identifiable, Hashable {
    public let id: UUID
    public let channel: String
    public let quarantineReason: String?
    public let filename: String?
    public let source: HeldSource
    public let receivedAt: Date

    public var headline: String { source.subject ?? filename ?? "Something with no subject" }
    public var sender: String { source.fromName ?? source.from ?? "an unknown sender" }
}

private struct AcceptBody: Encodable { let visibility: String }

extension API {
    public func held() async throws -> [HeldItem] { try await json("GET", "/quarantine") }
    public func acceptHeld(_ id: UUID, shared: Bool = true) async throws {
        let _: HeldItem = try await json("POST", "/quarantine/\(id.uuidString)/accept", body: AcceptBody(visibility: shared ? "shared" : "private"))
    }
    public func rejectHeld(_ id: UUID) async throws { _ = try await send("POST", "/quarantine/\(id.uuidString)/reject") }
}
