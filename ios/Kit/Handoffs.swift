// What was handed over and is waiting on an answer, what is handed to you, and how the work divides (familyos/handoffs.py, load.py). Counts only:
// recorded work, not a judgement about anyone.
import Foundation

public struct Handoff: Codable, Identifiable, Hashable {
    public let id: UUID
    public let title: String
    public let with: String?
    public let state: String
    public let since: Date
    public let hasBackup: Bool
    public let direction: String
}

private struct HandoffList: Codable { let items: [Handoff] }

public struct AdultWorkload: Codable, Identifiable, Hashable {
    public let memberId: UUID
    public let name: String
    public let open: Int
    public let handled30d: Int
    public var id: UUID { memberId }
}

public struct LoadMember: Codable, Identifiable, Hashable {
    public let memberId: UUID
    public let displayName: String
    public let carried: Int
    public let share: Int
    public let noticed: Int
    public let decided: Int
    public let acted: Int
    public var id: UUID { memberId }
}

public struct HouseholdLoad: Codable {
    public let days: Int
    public let total: Int
    public let undecided: Int
    public let missed: Int
    public let members: [LoadMember]
    public let note: String
}

extension API {
    public func handoffs() async throws -> [Handoff] { let out: HandoffList = try await json("GET", "/handoffs"); return out.items }
    public func workload() async throws -> [AdultWorkload] { try await json("GET", "/workload") }
    public func load(days: Int = 90) async throws -> HouseholdLoad { try await json("GET", "/load", query: ["days": String(days)]) }
}
