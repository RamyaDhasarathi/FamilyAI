// The school copilot (familyos/schoolday.py): what each child needs tomorrow, forms still to come back, and a draft absence note. Everything is
// read from notices the person may see; nothing is guessed and nothing is sent.
import Foundation

public struct SchoolDayItem: Codable, Hashable {
    public let title: String
    public let kind: String
    public let time: String?
    public let artifactId: UUID?
    public let undecided: Bool
    public let returned: Bool
}
public struct SchoolDayChild: Codable, Identifiable, Hashable {
    public var id: String { memberId?.uuidString ?? "none" }
    public let child: String
    public let `class`: String?
    public let school: String?
    public let items: [SchoolDayItem]
    public let bring: [String]
    public let memberId: UUID?
}
public struct SchoolDay: Codable {
    public let date: Date
    public let children: [SchoolDayChild]
    public let nothing: Bool
}
public struct SchoolForm: Codable, Identifiable, Hashable {
    public var id: UUID { obligationId }
    public let obligationId: UUID
    public let artifactId: UUID
    public let title: String
    public let dueDate: Date
    public let late: Bool
    /// "to return", "undecided" or "returned".
    public let state: String
    public let child: String?
    public let childId: UUID?
}
public struct AbsenceDraft: Codable { public let subject: String; public let body: String; public let school: String?; public let note: String }

private struct AbsenceBody: Encodable { let childId: UUID; let on: Date; let until: Date?; let reason: String? }

extension API {
    public func schoolTomorrow(on: Date? = nil) async throws -> SchoolDay {
        var query: [String: String] = [:]
        if let on { let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; f.locale = Locale(identifier: "en_US_POSIX"); query["on"] = f.string(from: on) }
        return try await json("GET", "/school/tomorrow", query: query)
    }
    public func schoolForms() async throws -> [SchoolForm] { try await json("GET", "/school/forms") }
    public func absenceNote(child: UUID, on: Date, until: Date?, reason: String?) async throws -> AbsenceDraft {
        try await json("POST", "/school/absence-note", body: AbsenceBody(childId: child, on: on, until: until, reason: reason))
    }
}
