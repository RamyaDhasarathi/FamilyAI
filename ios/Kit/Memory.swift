// What FamilyOS holds about the household (familyos/memory.py): each fact with its source, how it is known, who corrected it, when it was last
// confirmed and when to look at it again. A person can ask why, say it is right, and (a guardian, for a child's school) correct it.
import Foundation

public struct MemorySource: Codable, Hashable {
    public let type: String
    public let text: String
    public let at: Date?
    public let artifactId: UUID?
}
public struct MemoryCorrection: Codable, Hashable { public let by: String?; public let at: Date? }

public struct MemoryFact: Codable, Identifiable, Hashable {
    public var id: String { key }
    public let key: String
    public let kind: String
    public let subject: String?
    public let label: String
    public let value: String
    public let source: MemorySource
    public let howKnown: String
    public let confidence: String?
    public let corrected: MemoryCorrection?
    public let lastVerified: Date?
    public let reviewBy: Date?
    public let correctable: Bool
    public let howToCorrect: String?
    /// Only on a `why` reply: the steps in words.
    public let explanation: [String]?
}

private struct KeyBody: Encodable { let key: String }
private struct CorrectBody: Encodable { let key: String; let value: String?; let classLabel: String? }

extension API {
    public func memory() async throws -> [MemoryFact] { try await json("GET", "/memory") }
    public func memoryWhy(_ key: String) async throws -> MemoryFact { try await json("GET", "/memory/why", query: ["key": key]) }
    public func verifyMemory(_ key: String) async throws -> MemoryFact { try await json("POST", "/memory/verify", body: KeyBody(key: key)) }
    public func correctMemory(_ key: String, school: String?, classLabel: String?) async throws -> MemoryFact {
        try await json("POST", "/memory/correct", body: CorrectBody(key: key, value: school, classLabel: classLabel))
    }
}
