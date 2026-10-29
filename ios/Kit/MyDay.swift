// My day: the signed-in person's own page (GET /v1/me/day, familyos/myday.py),
// how FamilyOS may reach them (/v1/me/interruptions), what it has counted
// about the ideas they take (/v1/me/learned), and live product options for
// an idea (/v1/shop/*). Only the signed-in member's; nothing here is anyone else's.
import Foundation

public struct MyDay: Decodable {
    public let date: Date
    public let displayName: String
    public let role: String
    public let needs: [MyDayNeed]
    public let more: Int
    public let suggestions: [MyDayIdea]
    public let routines: [MyRoutine]
    public let reachMe: ReachPrefs
    public let learned: [LearnedKind]
    public let health: MyHealth

    public var isChild: Bool { role == "child" }
}

/// A brief item, as /me/day sends it. Leaner than `BriefItem`: the brief's
/// own route fills defaults this one does not, so most fields may be absent.
public struct MyDayNeed: Decodable, Identifiable, Hashable {
    public let reason: String
    public let title: String
    public let why: String?
    public let when: String?
    public let dueDate: Date?
    public let dueTime: String?
    public let action: String?
    public let subjectName: String?
    public let artifactId: UUID?
    public let obligationId: UUID?

    public var id: String { "\(reason)-\(obligationId?.uuidString ?? artifactId?.uuidString ?? title)" }
    /// Missed or overdue: drawn in the warning colour.
    public var isLate: Bool { reason == "missed" || reason == "overdue" }
}

/// An idea for the person, ranked by what they accept.
public struct MyDayIdea: Decodable, Identifiable, Hashable {
    public let key: String
    public let title: String
    public let why: String?
    public let dueDate: Date?
    public let link: String?
    public var id: String { key }
}

public struct MyRoutine: Decodable, Identifiable, Hashable {
    public let id: UUID
    public let instruction: String
    public let when: String
}

/// How much FamilyOS may say unprompted: a quiet window, a daily cap, the
/// hour of the morning message (none: the morning message is off).
public struct ReachPrefs: Codable, Hashable {
    public let quietFrom: Int?
    public let quietTo: Int?
    public let dailyCap: Int?
    public let morningHour: Int?
}

/// One kind of idea: how often it was added or waved away over 90 days.
public struct LearnedKind: Decodable, Identifiable, Hashable {
    public let kind: String
    public let accepted: Int
    public let dismissed: Int
    public let quiet: Bool
    public var id: String { kind }
}

public struct MyHealth: Decodable, Hashable {
    public let available: Bool
    public let sync: Bool
    public let line: String?
}

// MARK: product search

/// Live options from the shop catalogue. Fetched when asked, never kept;
/// the link is the seller's own, exactly as returned.
public struct ShopResults: Decodable {
    public let query: String?
    public let products: [ShopProduct]
    public let messages: [String]?
    public let error: String?
    public let note: String?
}

public struct ShopProduct: Decodable, Identifiable, Hashable {
    public struct Seller: Decodable, Hashable { public let name: String?; public let domain: String? }
    public struct Price: Decodable, Hashable { public let amount: Double; public let currency: String }
    public struct Rating: Decodable, Hashable { public let value: Double; public let scaleMax: Double?; public let count: Int? }
    public let title: String?
    public let seller: Seller?
    public let price: Price?
    public let url: String
    public let imageUrl: String?
    public let rating: Rating?
    public let options: String?
    public let available: Bool?
    /// False when the seller prices in another currency: it may not ship here.
    public let local: Bool?
    public var id: String { url }
}

extension API {
    public func myDay() async throws -> MyDay { try await json("GET", "/me/day") }

    /// Sets all four; no morning hour switches the morning message off.
    public func setReach(quietFrom: Int, quietTo: Int, dailyCap: Int, morningHour: Int?) async throws -> ReachPrefs {
        struct Body: Encodable { let quietFrom: Int; let quietTo: Int; let dailyCap: Int; let morningHour: Int?; let morningOff: Bool? }
        return try await json("PUT", "/me/interruptions", body: Body(quietFrom: quietFrom, quietTo: quietTo, dailyCap: dailyCap,
                                                                     morningHour: morningHour, morningOff: morningHour == nil ? true : nil))
    }

    /// Forget the counts: ideas go back to the default order.
    public func forgetLearned() async throws { _ = try await send("DELETE", "/me/learned") }

    public func shopEnabled() async throws -> Bool {
        struct R: Decodable { let enabled: Bool }
        let r: R = try await json("GET", "/shop/status"); return r.enabled
    }

    /// Options for an idea: the server searches for the thing, never the person.
    public func shopSearch(suggestion key: String) async throws -> ShopResults {
        try await json("GET", "/shop/search", query: ["suggestion": key])
    }
}
