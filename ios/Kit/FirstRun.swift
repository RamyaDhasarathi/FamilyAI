// The first-run screens (familyos/onboarding.py, docs/first-run.md): what the checklist says is left, founding a home from Google's word for an
// address, naming it, adding the family, and the two links a new person is offered (Telegram, mail and calendar).
import Foundation

/// What the app needs from a home that was just founded: the guardian's sign-in.
public struct HouseholdCreated: Decodable {
    public let credentials: SignedIn
}

/// Adding a member answers with the member, or, for someone who signs in, the member with a first token. Either way the id is what is needed.
public struct AddedMember: Decodable {
    private let id: UUID?
    private let member: Member?
    public var memberId: UUID? { id ?? member?.id }
}

private struct Named: Decodable { let name: String }

public struct MailboxAuthorization: Decodable { public let url: String }

/// A made-up person the first-run screens collect before anything is sent.
public struct NewChild: Identifiable, Hashable {
    public let id = UUID()
    public var name = ""
    public var age = ""

    public init() {}

    /// The server keeps a date of birth, and the screens ask only an age: the middle of the year it implies, so the age is right all year.
    public func dateOfBirth(today: Date = Date(), calendar: Calendar = .current) -> Date? {
        guard let years = Int(age.trimmingCharacters(in: .whitespaces)), (0...25).contains(years) else { return nil }
        let year = calendar.component(.year, from: today) - years
        return calendar.date(from: DateComponents(year: year, month: 7, day: 1))
    }

    public var isFilled: Bool { !name.trimmingCharacters(in: .whitespaces).isEmpty && dateOfBirth() != nil }
}

private struct FoundGuardian: Encodable { let displayName: String; let email: String }
private struct FoundHousehold: Encodable {
    let name: String
    let guardian: FoundGuardian
    let timezone: String
    let founding: String
}
private struct NewMember: Encodable {
    let displayName: String
    let role: String
    var email: String?
    var dateOfBirth: Date?
}

extension API {
    /// Found a home on Google's word for the address (the ticket from the redirect). The country is the server's default, India; the zone is this phone's.
    public func foundHousehold(name: String, guardianName: String, email: String, ticket: String) async throws -> HouseholdCreated {
        try await json("POST", "/households", body: FoundHousehold(
            name: name, guardian: FoundGuardian(displayName: guardianName, email: email),
            timezone: TimeZone.current.identifier, founding: ticket), signed: false)
    }

    public func renameHousehold(_ name: String) async throws {
        let _: Named = try await json("PATCH", "/household", body: ["name": name])
    }

    @discardableResult
    public func addChild(_ name: String, born: Date) async throws -> AddedMember {
        try await json("POST", "/household/members", body: NewMember(displayName: name, role: "child", dateOfBirth: born))
    }

    /// An adult is added with the address they sign in with, then mailed their way in.
    public func addAdultAndInvite(_ name: String, email: String) async throws {
        let added: AddedMember = try await json("POST", "/household/members", body: NewMember(displayName: name, role: "adult", email: email))
        if let id = added.memberId { _ = try await invite(id) }
    }

    /// The phone's own consent: Google's page opens in the app's web session, and the callback comes back through the URL scheme with a
    /// finish token only this signed-in member can spend (familyos/intake/mailbox.py, park and finish).
    public func mailboxAuthorizationURL() async throws -> URL {
        let out: MailboxAuthorization = try await json("POST", "/google/mailboxes/authorize", query: ["native": "true"])
        guard let url = URL(string: out.url) else { throw APIError(status: 0, detail: "Google gave no address to open.") }
        return url
    }

    public func finishMailbox(_ finish: String) async throws {
        _ = try await send("POST", "/google/mailboxes/finish", body: try API.encoder.encode(["finish": finish]))
    }
}

/// What came back from Google to the app: the token to finish with, or why it did not go through.
public enum MailboxOutcome: Equatable {
    case finish(String)
    case cancelled
    case failed

    public static func parse(_ url: URL) -> MailboxOutcome? {
        guard url.host == "mailbox", let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems else { return nil }
        if let token = items.first(where: { $0.name == "finish" })?.value, !token.isEmpty { return .finish(token) }
        switch items.first(where: { $0.name == "result" })?.value {
        case "access_denied", "cancelled": return .cancelled
        default: return .failed
        }
    }
}
