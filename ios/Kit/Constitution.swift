// Rules and access (familyos/circle.py, rules.py): the household's authority in sentences. What is always true, the rules a guardian can switch,
// and for each person what they see and why. Readable by any member: a person is entitled to know who sees what.
import Foundation

public struct RuleOption: Codable, Hashable { public let id: UUID; public let name: String }

public struct HouseholdRule: Codable, Identifiable, Hashable {
    public var id: String { key }
    public let key: String
    public let title: String
    public let sentence: String
    public let on: Bool
    public let fixed: Bool
    public let whyFixed: String?
    /// "switch", "text" (a place), "number" or "who".
    public let kind: String?
    public let text: String?
    public let value: Int?
    public let unit: String?
    public let options: [RuleOption]?
    public let memberId: UUID?
    public var isSwitch: Bool { (kind ?? "switch") == "switch" }
}

public struct PersonAccess: Codable, Identifiable, Hashable {
    public var id: UUID { memberId }
    public let memberId: UUID
    public let displayName: String
    public let role: String
    public let circleWords: String?
    public let sees: [String]
}

public struct Constitution: Codable {
    public let walls: [String]
    public let rules: [HouseholdRule]
    public let people: [PersonAccess]
}

extension API {
    public func constitution() async throws -> Constitution { try await json("GET", "/household/constitution") }
}
