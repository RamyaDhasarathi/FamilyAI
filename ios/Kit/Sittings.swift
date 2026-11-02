// Rails (which door each school's notices come through), harvests (a sitting where the person signs in to a site themselves and picks what to keep),
// and taking everything out or erasing it (familyos/rails.py, execution/harvest.py, export.py, erasure.py). No credential is ever taken in a sitting.
import Foundation

public struct RailRow: Codable, Identifiable, Hashable {
    public let rail: String
    public let label: String
    public let first: Int
    public let echo: Int
    public let empty: Int
    public let deliveries: Int
    public var id: String { rail }
}

public struct SchoolRails: Codable, Identifiable, Hashable {
    public let schoolId: UUID
    public let school: String
    public let notices: Int
    public let rails: [RailRow]
    public let said: String?
    public var id: UUID { schoolId }
}

public struct Sitting: Codable, Identifiable, Hashable {
    public let id: UUID
    public let label: String
    public let liveUrl: String?
    public let allowHosts: [String]
    public let state: String
    public let expiresAt: Date
    public var isOpen: Bool { state == "collecting" || state == "review" }
}

public struct SittingPage: Codable, Identifiable, Hashable {
    public let id: UUID
    public let url: String
    public let title: String
    public let text: String
    public let bytes: Int
    public let decision: String?
}

private struct NewSitting: Encodable { let label: String; let allowHosts: [String]; let minutes: Int }
private struct ConfirmName: Encodable { let confirmName: String }

extension API {
    public func rails() async throws -> [SchoolRails] { try await json("GET", "/rails") }

    public func sittings() async throws -> [Sitting] { try await json("GET", "/harvests") }
    public func beginSitting(label: String, hosts: [String], minutes: Int) async throws -> Sitting {
        try await json("POST", "/harvests", body: NewSitting(label: label, allowHosts: hosts, minutes: minutes))
    }
    public func sittingPages(_ id: UUID) async throws -> [SittingPage] { try await json("GET", "/harvests/\(id.uuidString)/candidates") }
    public func keepPage(_ id: UUID) async throws { _ = try await send("POST", "/harvest-candidates/\(id.uuidString)/keep") }
    public func discardPage(_ id: UUID) async throws { _ = try await send("DELETE", "/harvest-candidates/\(id.uuidString)") }
    public func finishSitting(_ id: UUID) async throws { _ = try await send("POST", "/harvests/\(id.uuidString)/finish") }

    /// Everything the member can see (or, for a guardian, what is held about one child), as a zip written to a temporary file for the share sheet.
    public func exportFile(of member: UUID? = nil) async throws -> URL {
        let (data, resp) = try await send("GET", member.map { "/members/\($0.uuidString)/export" } ?? "/export")
        let disposition = resp.value(forHTTPHeaderField: "Content-Disposition") ?? ""
        let name = disposition.components(separatedBy: "filename=\"").dropFirst().first?.components(separatedBy: "\"").first ?? "familyos-export.zip"
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(name.replacingOccurrences(of: "/", with: "-"))
        try data.write(to: url, options: .completeFileProtection)
        return url
    }

    public func eraseChild(_ id: UUID) async throws -> ErasureStarted { try await json("POST", "/members/\(id.uuidString)/erase") }
    public func eraseHousehold(confirmName: String) async throws -> ErasureStarted {
        try await json("POST", "/household/erase", body: ConfirmName(confirmName: confirmName))
    }
}
