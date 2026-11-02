// The household's security from the phone: the family key held as word
// shares, where the household's words are read, this member's passkeys, and
// a member's invitation. Shares are secrets: they pass through these calls
// and are never kept, logged or written anywhere by the app.
import Foundation

/// Whether the server or the family holds the household's key, and, held by
/// the family, whether it is open now. `threshold` and `shares` are nil until
/// shares have been made.
public struct FamilyKeyStatus: Codable, Hashable {
    public let mode: String
    public let threshold: Int?
    public let shares: Int?
    public let pending: Bool
    public let locked: Bool
    public let unlockedForMinutes: Int
    /// One recovery phrase and trusted devices ("Make it private"), as against shares among several people.
    public let simple: Bool?

    public var heldByFamily: Bool { mode == "family" }
    public var isSimple: Bool { simple == true }
}

/// The one-tap switch-on as the server makes it: a recovery phrase and the secret of the device made for the switch-on, both shown once and
/// never stored by the server or by the app. Not Codable on purpose, so it cannot be written down.
public struct FamilyKeySimple: Decodable {
    public struct Device: Decodable { public let id: String; public let secret: String; public let label: String? }
    public let phrase: String
    public let device: Device
    public let note: String?
}

/// A replacement recovery phrase, shown once.
public struct FamilyKeyNewPhrase: Decodable { public let phrase: String; public let note: String? }

/// Shares as the server makes them: shown once, never stored by the server
/// or by the app. Not Codable on purpose, so it cannot be written down.
public struct FamilyKeyShares: Decodable {
    public let shares: [String]
    public let threshold: Int
    public let count: Int
    public let note: String?
}

public enum FamilyKey {
    /// Every 33 words is one share, whatever whitespace or line breaks were
    /// pasted between them: the console's `parseShares`. Words past the last
    /// whole share are dropped.
    public static let wordsPerShare = 33

    public static func parseShares(_ text: String) -> [String] {
        let words = text.lowercased().split(whereSeparator: { $0.isWhitespace }).map(String.init)
        return stride(from: 0, to: words.count - wordsPerShare + 1, by: wordsPerShare).map { words[$0..<$0 + wordsPerShare].joined(separator: " ") }
    }

    /// How many words were pasted, for the count under the box.
    public static func wordCount(_ text: String) -> Int { text.split(whereSeparator: { $0.isWhitespace }).count }
}

/// One way the household's words can be read: a model, its trust class and where it runs.
public struct ModelProfile: Codable, Hashable, Identifiable {
    public let name: String
    public let kind: String?
    public let model: String?
    public let trust: String
    public let `where`: String?
    public let available: Bool?
    public var id: String { name }
    public var title: String { name == "default" ? "Default" : name }
}

public struct ModelRouting: Codable, Hashable {
    public var extraction: String
    public var ask: String
    public var floor: String
}

/// What each trust class means, in the server's words.
public struct TrustWords: Codable, Hashable {
    public let cloud: String
    public let confidential: String
    public let own: String
}

public struct HouseholdModels: Codable, Hashable {
    public let profiles: [ModelProfile]
    public let routing: ModelRouting
    public let trust: TrustWords

    /// The classes, least private first: the floor is one of these.
    public static let classes = ["cloud", "confidential", "own"]
}

/// A passkey this member made in the console; only its public half is on the server.
public struct Passkey: Codable, Hashable, Identifiable {
    public let id: UUID
    public let label: String
    public let rpId: String?
    public let backedUp: Bool
    public let createdAt: Date
    public let lastUsedAt: Date?
}

/// A member's way in: a single-use link good for a week. The token is a
/// credential until it is used; it is shown, not kept.
public struct Invitation: Decodable {
    public let memberId: String
    public let token: String
    public let link: String?
    public let emailed: Bool
    public let expiresAt: Date?

    /// The console's address with the link in it, the way the console composes it.
    public var consoleURL: URL? {
        guard let base = Server.baseURL else { return nil }
        let root = base.absoluteString.hasSuffix("/") ? String(base.absoluteString.dropLast()) : base.absoluteString
        let enc = token.addingPercentEncoding(withAllowedCharacters: .alphanumerics.union(.init(charactersIn: "-_.~"))) ?? token
        return URL(string: root + "/app/#link=" + enc)
    }
}

/// Whether a member has signed in yet, and when they were last invited.
/// Read from the same household answer as the members, kept apart from
/// `Member` so the shared model stays as it is.
public struct MemberJoining: Decodable, Hashable {
    public let id: UUID
    public let joined: Bool?
    public let invitedAt: Date?
}

extension API {
    // MARK: family key

    public func familyKey() async throws -> FamilyKeyStatus { try await json("GET", "/household/family-key") }

    /// Makes the shares; nothing changes until t of them are confirmed. Guardians only.
    public func beginFamilyKey(threshold: Int, count: Int) async throws -> FamilyKeyShares {
        try await json("POST", "/household/family-key/begin", body: ["threshold": threshold, "count": count])
    }
    public func confirmFamilyKey(shares: [String]) async throws -> FamilyKeyStatus {
        try await json("POST", "/household/family-key/confirm", body: SharesBody(shares: shares))
    }
    public func unlockFamilyKey(shares: [String]) async throws -> FamilyKeyStatus {
        try await json("POST", "/household/family-key/unlock", body: SharesBody(shares: shares))
    }
    public func lockFamilyKey() async throws -> FamilyKeyStatus { try await json("POST", "/household/family-key/lock") }
    public func disableFamilyKey(shares: [String]) async throws -> FamilyKeyStatus {
        try await json("POST", "/household/family-key/disable", body: SharesBody(shares: shares))
    }
    /// New shares for the same key; the old ones stop opening anything. Guardians only.
    public func reshareFamilyKey(shares: [String], threshold: Int, count: Int) async throws -> FamilyKeyShares {
        try await json("POST", "/household/family-key/reshare", body: ReshareBody(shares: shares, threshold: threshold, count: count))
    }

    // MARK: make it private (one recovery phrase)

    /// Makes the recovery phrase and a device secret; nothing changes until `finishPrivate`. Guardians only.
    public func makePrivate(label: String) async throws -> FamilyKeySimple {
        try await json("POST", "/household/family-key/simple", body: ["label": label])
    }
    /// Switches on once the device secret has been handed back. The phone keeps no device secret (no passkey unlock here yet), so the caller retires the device straight after.
    public func finishPrivate(deviceId: String, deviceSecret: String) async throws -> FamilyKeyStatus {
        try await json("POST", "/household/family-key/simple/done", body: DeviceBody(deviceId: deviceId, deviceSecret: deviceSecret))
    }
    public func removeFamilyKeyDevice(_ id: String) async throws { _ = try await send("DELETE", "/household/family-key/devices/\(id.lowercased())") }
    public func recoverFamilyKey(phrase: String) async throws -> FamilyKeyStatus {
        try await json("POST", "/household/family-key/recover", body: ["phrase": phrase])
    }
    /// A fresh phrase while the household is open; the old one stops working. Guardians only.
    public func newRecoveryPhrase() async throws -> FamilyKeyNewPhrase { try await json("POST", "/household/family-key/new-phrase") }

    // MARK: where the words are read

    public func householdModels() async throws -> HouseholdModels { try await json("GET", "/household/models") }
    /// A choice below the floor is refused with the server's own sentence, as the error.
    public func setHouseholdModels(extraction: String?, ask: String?, floor: String?) async throws -> HouseholdModels {
        try await json("PUT", "/household/models", body: ModelRoutingBody(extraction: extraction, ask: ask, floor: floor))
    }

    // MARK: passkeys

    public func passkeys() async throws -> [Passkey] { try await json("GET", "/me/passkeys") }
    public func removePasskey(_ id: UUID) async throws { _ = try await send("DELETE", "/me/passkeys/\(id.uuidString.lowercased())") }

    // MARK: joining

    /// A fresh single-use link for an adult, also emailed when mail is set up. Guardians only.
    public func invite(_ member: UUID) async throws -> Invitation {
        try await json("POST", "/members/\(member.uuidString.lowercased())/invite", body: ["send_email": true])
    }
    /// Each member's joined flag and last invitation, by id.
    public func joining() async throws -> [UUID: MemberJoining] {
        struct H: Decodable { let members: [MemberJoining] }
        let h: H = try await json("GET", "/household")
        return Dictionary(h.members.map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a })
    }
}

struct SharesBody: Encodable { let shares: [String] }
struct DeviceBody: Encodable { let deviceId: String; let deviceSecret: String }
struct ReshareBody: Encodable { let shares: [String]; let threshold: Int; let count: Int }
struct ModelRoutingBody: Encodable { let extraction: String?; let ask: String?; let floor: String? }
