// What the API says, as the app reads it. Only the fields the app uses;
// anything else the server sends is ignored, so the server can grow
// without the app breaking.
import Foundation

public struct Member: Codable, Identifiable, Hashable {
    public let id: UUID
    public let householdId: UUID
    public let displayName: String
    public let role: String
    public let email: String?
    public let school: String?
    public let classLabel: String?
    public let telegramLinked: Bool?
    public let dateOfBirth: Date?

    public var isChild: Bool { role == "child" }
    public var age: Int? { dateOfBirth.flatMap { Calendar.current.dateComponents([.year], from: $0, to: Date()).year } }
}

public struct Household: Codable {
    public let id: UUID
    public let name: String
    public let inboundAddress: String
    public let telegramBot: String?
    public let members: [Member]
    public let country: String?
    public let timezone: String?
    public let currency: String?
}

public struct SignedIn: Codable {
    public let member: Member
    public let token: String
    public init(member: Member, token: String) { self.member = member; self.token = token }
}

public struct BriefItem: Codable, Identifiable, Hashable {
    public let reason: String
    public let rank: Int
    public let title: String
    public let why: String
    public let when: String?
    public let dueDate: Date?
    public let dueTime: String?
    public let action: String?
    public let status: String?
    public let optional: Bool
    public let clashes: [String]?
    public let assignedByName: String?
    public let payUrl: String?
    public let handledByName: String?
    public let note: String?
    public let contested: Bool
    public let subjectName: String?
    public let subjectMemberId: UUID?
    public let obligationId: UUID?
    public let amendmentId: UUID?
    public let artifactId: UUID?
    public let travelMinutes: Int?
    public let leaveBy: String?

    public var id: String { "\(reason)-\(rank)-\(obligationId?.uuidString ?? artifactId?.uuidString ?? title)" }
}

/// Public context the household switched on: the weather for home, the holidays coming,
/// and the school run from home (typical minutes; minutes now, before school, when live traffic is on).
public struct BriefContext: Codable {
    public let weather: String?
    public let holidays: [BriefHoliday]?
    public let schoolRuns: [SchoolRun]?
}

public struct SchoolRun: Codable, Hashable {
    public let school: String
    public let minutes: Int
    public let liveMinutes: Int?
    public let delayMinutes: Int?
    public let leaveBy: String?
    public let startsAt: String?

    /// "41 min now to Aachi Global School, leave by 7:09 am" or "31 min to Aachi Global School".
    public var line: String {
        var s = liveMinutes.map { "\($0) min now" } ?? "\(minutes) min"
        s += " to \(school)"
        if let d = delayMinutes, d >= 3 { s += " (\(d) worse than usual)" }
        if let l = leaveBy { s += ", leave by \(l)" }
        return s
    }
}

public struct BriefHoliday: Codable, Hashable {
    public let date: Date
    public let name: String
}

public struct Brief: Codable {
    public let date: Date
    public let displayName: String
    public let items: [BriefItem]
    public let counts: [String: Int]
    public let more: Int
    public let context: BriefContext?
}

public struct InboxRow: Codable, Identifiable, Hashable {
    public let id: UUID
    public let channel: String
    public let visibility: String
    public let receivedAt: Date
    public let filename: String?
    public let mediaType: String
    public let headline: String?
    public let fromLabel: String
    public let subjectMemberIds: [UUID]
    public let assignedTo: UUID?
    public let assignedNote: String?
    public let handledAt: Date?
    public let handledNote: String?
    public let dates: Int
    public let open: Int
    public let attachments: Int
    public let preview: [String]
    public let nextDate: Date?
    public let reason: String?
    public let state: String
    public let category: String

    public var title: String { headline ?? filename ?? fromLabel }
    public var isPicture: Bool { mediaType.hasPrefix("image/") }
}

public extension InboxRow {
    /// Folded away unless searched for: bank alerts are lines in Money, promos
    /// and newsletters are noise.
    static let quietCategories: Set<String> = ["banking", "promo", "newsletter", "developer"]
    /// Not about a person: a delivery, a shop, a subscription, a trade. Those
    /// are records in Money and Investments, not news about the family.
    static let recordCategories: Set<String> = ["food", "shopping", "subscriptions", "trading"]
    var isQuiet: Bool { Self.quietCategories.contains(category) }
    /// Worth a person's page: neither noise nor a mere record.
    var isAboutPeople: Bool { !isQuiet && !Self.recordCategories.contains(category) }
}

public struct Artifact: Codable, Identifiable {
    public let id: UUID
    public let parentId: UUID?
    public let submittedBy: UUID?
    public let channel: String
    public let visibility: String
    public let status: String
    public let filename: String?
    public let mediaType: String
    public let note: String?
    public let subjectMemberIds: [UUID]
    public let children: [UUID]
    public let assignedTo: UUID?
    public let assignedNote: String?
    public let assignedBy: UUID?
    public let handledAt: Date?
    public let handledBy: UUID?
    public let handledNote: String?
    public let receivedAt: Date
    public let source: [String: JSONValue]

    public var isPicture: Bool { mediaType.hasPrefix("image/") }
    /// A photograph the family shared, not a picture that is really a notice.
    public var isMemory: Bool {
        guard isPicture, channel != "errand" else { return false }
        if case .string("document")? = source["picture"] { return false }
        return true
    }
    public var headline: String? {
        if case let .string(s)? = source["headline"] { return s }
        if case let .string(s)? = source["subject"] { return s }
        return nil
    }
    public var sender: String? {
        if case let .string(s)? = source["from"] { return s }
        return nil
    }
}

public struct Claim: Codable, Identifiable, Hashable {
    public let id: UUID
    public let kind: String
    public let title: String
    public let date: Date?
    public let endDate: Date?
    public let dateText: String?
    public let timeText: String?
    public let place: String?
    public let amountText: String?
    public let subjectName: String?
    public let requires: [String]
    public let optional: Bool
    public let uncertain: Bool
}

public struct Extraction: Codable {
    public let actionable: Bool
    public let nonActionableReason: String?
    public let notes: [String]
    public let claims: [Claim]
}

public struct ArtifactExtraction: Codable {
    public let artifactId: UUID
    public let extraction: Extraction?
    public let jobStatus: String?
    public let jobError: String?
}

public struct Obligation: Codable, Identifiable, Hashable {
    public let id: UUID
    public let artifactId: UUID
    public let subjectMemberId: UUID?
    public let kind: String
    public let action: String
    public let title: String
    public let dueDate: Date?
    public let endDate: Date?
    public let dueTime: String?
    public let optional: Bool
    public let status: String
    public let supersededAt: Date?
}

public struct Handled: Codable {
    public let id: UUID
    public let handledAt: Date?
    public let handledNote: String?
}

public struct Assigned: Codable {
    public let id: UUID
    public let assignedTo: UUID?
    public let assignedNote: String?
}

public struct Citation: Codable, Hashable {
    public let ref: String
    public let kind: String
}

public struct Answer: Codable {
    public let answer: String
    public let grounded: Bool
    public let citations: [Citation]
    public let note: String?
}

public struct Device: Codable, Identifiable, Hashable {
    public let id: UUID
    public let label: String?
    public let createdAt: Date
    public let lastUsedAt: Date?
}

public struct DeviceIssued: Codable {
    public let device: Device
    public let token: String
    public let shareUrl: String
}

public struct ShareResult: Codable {
    public let duplicate: Bool
    public let tagged: [String]?
    public let message: String
}

/// A JSON value of any shape, for the parts of a reply that are a free dict.
public enum JSONValue: Codable, Hashable {
    case string(String), number(Double), bool(Bool), null
    case array([JSONValue]), object([String: JSONValue])

    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let b = try? c.decode(Bool.self) { self = .bool(b) }
        else if let n = try? c.decode(Double.self) { self = .number(n) }
        else if let s = try? c.decode(String.self) { self = .string(s) }
        else if let a = try? c.decode([JSONValue].self) { self = .array(a) }
        else { self = .object(try c.decode([String: JSONValue].self)) }
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .null: try c.encodeNil()
        case .bool(let b): try c.encode(b)
        case .number(let n): try c.encode(n)
        case .string(let s): try c.encode(s)
        case .array(let a): try c.encode(a)
        case .object(let o): try c.encode(o)
        }
    }
}

// MARK: money, plans, errands, calendar

public struct MoneyCharge: Codable, Identifiable, Hashable {
    public let messageId: UUID
    public let artifactId: UUID
    public let merchant: String
    public let category: String
    public let amount: Double
    public let currency: String
    public let date: Date
    public let title: String
    public let headline: String
    public let upcoming: Bool
    public let due: Date?
    public let settlesMessageId: UUID?
    public let settlesDue: Date?
    public var id: UUID { messageId }
}

public struct MoneyRecurring: Codable, Identifiable, Hashable {
    public let merchant: String
    public let category: String
    public let currency: String
    public let cadence: String
    public let manageUrl: String?
    public let lastAmount: Double?
    public let lastDate: Date?
    public let nextDate: Date
    public let nextAmount: Double
    public let times: Int
    public let total: Double
    public let artifactId: UUID
    public var id: String { merchant + cadence + currency }
}

public struct MoneyTotal: Codable, Hashable {
    public let category: String?
    public let merchant: String?
    public let currency: String
    public let total: Double
    public let times: Int?
    public let previous: Double?
}

public struct MoneySpend: Codable {
    public let days: Int
    public let charges: Int
    public let byCategory: [MoneyTotal]
    public let byMerchant: [MoneyTotal]
}

public struct MoneyService: Codable, Identifiable, Hashable {
    public let date: Date
    public let merchant: String
    public let kind: String
    public let what: String
    public let amount: Double
    public let currency: String
    public let artifactId: UUID
    public var id: String { artifactId.uuidString + kind }
}

public struct MoneyServices: Codable {
    public let timeline: [MoneyService]
    public let lastDone: [MoneyService]
}

public struct RunningLow: Codable, Identifiable, Hashable {
    public let item: String
    public let itemKey: String
    public let merchant: String
    public let times: Int
    public let everyDays: Int
    public let lastOn: Date
    public let expectedOn: Date
    public let status: String
    public let reorderUrl: String?
    public var id: String { itemKey }
}

public struct Money: Codable {
    public let days: Int
    public let charges: [MoneyCharge]
    public let recurring: [MoneyRecurring]
    public let month: MoneySpend
    public let services: MoneyServices
    public let runningLow: [RunningLow]
}

public struct Plan: Codable, Identifiable, Hashable {
    public let id: UUID
    public let title: String
    public let brief: String
    public let status: String
    public let shape: String
    public let startsOn: Date?
    public let endsOn: Date?
    public let summary: String?
    public let todos: [PlanTodo]
}

public struct PlanTodo: Codable, Identifiable, Hashable {
    public let id: UUID
    public let title: String
    public let doneAt: Date?
}

public struct Errand: Codable, Identifiable, Hashable {
    public let id: UUID
    public let service: String
    public let kind: String
    public let title: String
    public let status: String
    public let paramsSha256: String?
    public let createdBy: UUID?
    public let spec: [String: JSONValue]?
    public let error: String?
    public let outcome: [String: JSONValue]?
    public let createdAt: Date?
    public let approvedAt: Date?
    public let updatedAt: Date?
    public let endedAt: Date?

    public var what: String { if case .string(let s)? = spec?["what"] { return s }; return title }
    public var runsOnPhone: Bool { if case .string("phone")? = spec?["run_on"] { return true }; return false }
    /// An app on the phone rather than a site: read through the phone's own
    /// hands (the FamilyOSDriver test runner), not the app's web view.
    public var isPhoneApp: Bool {
        if case .object(let w)? = spec?["where"], case .string("the phone")? = w["on"] { return true }
        return false
    }
    public var appLabel: String? {
        if case .object(let w)? = spec?["where"], case .string(let s)? = w["label"] { return s }
        return nil
    }

    public var isLive: Bool { !["done", "cancelled", "failed", "stopped"].contains(status) }
    /// Worth a Live Activity: something is actually moving (running, or
    /// stopped where a person must look) and it moved recently. An approved
    /// errand waiting for a phone, or a run the server lost track of, is not
    /// "running" on anyone's island.
    public var isMoving: Bool {
        guard status == "running" || status == "needs_you" else { return false }
        let since = updatedAt ?? approvedAt ?? createdAt ?? .distantPast
        return Date().timeIntervalSince(since) < (status == "running" ? 30 * 60 : 24 * 3600)
    }
    /// A string inside the spec, by path: spec("where", "label").
    public func spec(_ path: String...) -> String? {
        var cur: JSONValue? = spec.map { .object($0) }
        for key in path { guard case .object(let o)? = cur else { return nil }; cur = o[key] }
        switch cur {
        case .string(let s)?: return s
        case .number(let n)?: return n == n.rounded() ? String(Int(n)) : String(n)
        case .bool(let b)?: return b ? "yes" : "no"
        default: return nil
        }
    }
    /// The steps the run wrote down: when, what it said, the picture it took.
    public var steps: [ErrandStep] {
        guard case .array(let arr)? = outcome?["steps"] else { return [] }
        return arr.compactMap { v in
            guard case .object(let o) = v, case .string(let said)? = o["said"] else { return nil }
            let at: Date? = { if case .string(let s)? = o["at"] { return API.parseDate(s) }; return nil }()
            let pic: UUID? = { if case .string(let s)? = o["artifact_id"] { return UUID(uuidString: s) }; return nil }()
            return ErrandStep(said: said, at: at, artifactId: pic)
        }
    }
    public var stopRules: [String] {
        switch spec?["stop_rules"] {
        case .array(let a)?: return a.compactMap { if case .string(let s) = $0 { return s }; return nil }
        case .object(let o)?: return o.keys.sorted().compactMap { k in if case .string(let v)? = o[k] { return "\(k.replacingOccurrences(of: "_", with: " ")): \(v.replacingOccurrences(of: "_", with: " "))" }; return nil }
        default: return []
        }
    }
    public var statusLabel: String {
        ["proposed": "waiting for approval", "needs_you": "needs you"][status] ?? status
    }
}

public struct CalendarEvent: Codable, Identifiable, Hashable {
    public let id: UUID
    public let summary: String
    public let startsAt: Date
    public let endsAt: Date
    public let allDay: Bool
}

public struct GoogleSignIn: Codable { public let url: String }

// MARK: to-dos, documents, chat

/// Something FamilyOS could start doing, or will do, in the family's names.
public struct Offer: Codable, Identifiable, Hashable {
    public let key: String
    public let kind: String
    public let title: String
    public let body: String
    public let limit: String
    public let fyi: Bool
    public let acceptLabel: String?
    public let ask: String?
    public var id: String { key }
}

public struct OfferDone: Codable {
    public let key: String
    public let done: String
    public let ask: String?
}

public struct Todo: Codable, Identifiable, Hashable {
    public let id: UUID
    public let title: String
    public let note: String?
    public let dueDate: Date?
    public let dueTime: String?
    public let assignedTo: UUID?
    public let doneAt: Date?
}

public struct Document: Codable, Identifiable, Hashable {
    public let id: UUID
    public let artifactId: UUID
    public let kind: String
    public let label: String
    public let title: String
    public let holderMemberId: UUID?
    public let holderName: String?
    public let issuer: String?
    public let identifierTail: String?
    public let validFrom: Date?
    public let expiresOn: Date?
    public let status: String
    public let daysLeft: Int?
}

public struct DocumentCheck: Codable, Hashable {
    public let kind: String
    public let title: String
    public let why: String
    public let artifactId: UUID?
}

public struct Documents: Codable {
    public let documents: [Document]
    public let checks: [DocumentCheck]
}

public struct ChatMessage: Codable, Hashable {
    public let role: String
    public let content: String
    public init(role: String, content: String) { self.role = role; self.content = content }
}

public struct ChatCitation: Codable, Hashable {
    public let ref: String
    public let kind: String
    public let text: String
    public let artifactId: UUID?
    public let obligationId: UUID?
}

public struct ChatProposal: Codable, Hashable {
    public let kind: String
    public let ok: Bool
    public let why: String?
    public let artifactId: UUID?
    public let headline: String?
    public let obligationId: UUID?
    public let memberId: UUID?
    public let memberName: String?
    public let title: String?
    public let dueDate: Date?
    public let dueTime: String?
    public let note: String?
    public let status: String?
    public let brief: String?
    public let shape: String?
    public let service: String?
    public let label: String?
    public let what: String?
    public let look: Bool?
}

public struct ChatTurn: Codable {
    public let say: String
    public let grounded: Bool
    public let citations: [ChatCitation]
    public let proposals: [ChatProposal]
    public let model: String
    public let note: String?
}

struct ChatBody: Encodable { let message: String; let history: [ChatMessage] }
struct TodoBody: Encodable { let title: String; let dueDate: Date?; let dueTime: String?; let assignedTo: UUID?; let note: String? }
struct PlanBody: Encodable { let brief: String; let shape: String }

struct ErrandWhenBody: Encodable { let date: Date?; let time: String?; let part: String }
struct ErrandSpecBody: Encodable { let what: String; let details: String?; let when: ErrandWhenBody; let maxAmount: Double?; let currency: String; let payment: String; let bundle: String? }
struct ErrandBody: Encodable { let service: String; let kind: String; let title: String; let spec: ErrandSpecBody }

public struct ErrandStep: Identifiable, Hashable {
    public var id: String { "\(at?.timeIntervalSince1970 ?? 0)-\(said)" }
    public let said: String
    public let at: Date?
    public let artifactId: UUID?
}

public struct TelegramLink: Codable {
    public let url: String
    public let botUsername: String
    public let expiresInMinutes: Int
}


public extension String {
    /// Nil when there is nothing to show, so a line can be skipped in one `if let`.
    var nilIfEmpty: String? { isEmpty ? nil : self }
}
