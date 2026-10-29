// The Family Activity Ledger (familyos/activity.py): each thing FamilyOS or a person did, as a receipt, with an undo only where the server says it can
// honestly be undone (nothing has changed since). A guardian sees the household's; anyone else only their own.
import Foundation

public struct ActivityReceipt: Codable, Hashable {
    public let observed: String?
    public let inferred: String?
    public let rule: String?
    public let approvedBy: String?
    public let changed: String?
}

public struct ActivityUndo: Codable, Hashable {
    public let label: String
}

public struct ActivityItem: Codable, Identifiable, Hashable {
    public let id: Int
    public let at: Date
    public let who: String
    public let said: String
    public let action: String
    public let receipt: ActivityReceipt
    public let undo: ActivityUndo?
}

public struct ActivityUndone: Codable {
    public let undone: String
}

extension API {
    /// Newest first. `before` is the id of the oldest row already shown.
    public func activity(limit: Int = 50, before: Int? = nil) async throws -> [ActivityItem] {
        var query = ["limit": String(limit)]
        if let before { query["before"] = String(before) }
        return try await json("GET", "/activity", query: query)
    }
    public func undoActivity(_ id: Int) async throws -> ActivityUndone { try await json("POST", "/activity/\(id)/undo") }
}
