// The household as a graph of what touches what: people, notices, dates,
// documents, warranties, medicines, shops and clinics. The server builds it
// per request from the record (familyos/graph.py); the app only reads it.
// Every link carries the notice it came from.
import Foundation

/// One thing on the map. `ref` is `type:id` (an org's id is a slug); the
/// dates come as days and are kept as text, shown through `API.parseDate`.
public struct GraphNode: Codable, Identifiable, Hashable {
    public let ref: String
    public let type: String
    public let label: String
    public let role: String?
    public let due: String?
    public let status: String?
    public let kind: String?
    public let expiresOn: String?
    public let warrantyUntil: String?
    public let returnBy: String?
    public var id: String { ref }
}

/// One link on the way to a node, with the sentence it reads as and the notice it is from.
public struct GraphStep: Codable, Hashable {
    public let from: String
    public let relation: String
    public let to: String
    public let sourceArtifactId: UUID?
    public let quote: String?
    public let phrase: String?
}

/// A node near the centre: how many links away, and the links that reach it.
public struct GraphConnection: Codable, Identifiable, Hashable {
    public let node: GraphNode
    public let distance: Int
    public let path: [GraphStep]
    public var id: String { node.ref }
    /// The link that touches this node: its sentence and notice are the ones to show.
    public var last: GraphStep? { path.last }
}

public struct GraphTouches: Codable, Hashable {
    public let entity: GraphNode
    public let connections: [GraphConnection]
    public let count: Int
}

/// What the shape of the record shows that nobody asked about: a busy week,
/// a document tied to no one, a warranty about to end.
public struct GraphInsight: Codable, Identifiable, Hashable {
    public struct Item: Codable, Hashable { public let ref: String; public let label: String; public let due: String? }
    public let kind: String
    public let key: String
    public let ref: String
    public let title: String
    public let why: String
    public let items: [Item]?
    public var id: String { key }
}

extension API {
    /// Everything within `depth` links of `ref`, nearest first.
    public func graphTouches(ref: String, depth: Int = 2) async throws -> GraphTouches {
        try await json("GET", "/graph/touches", query: ["ref": ref, "depth": String(depth)])
    }
    /// People, shops, clinics, documents and dates whose name contains the words.
    public func graphFind(_ q: String, limit: Int = 8) async throws -> [GraphNode] {
        try await json("GET", "/graph/find", query: ["q": q, "limit": String(limit)])
    }
    public func graphInsights() async throws -> [GraphInsight] { try await json("GET", "/graph/insights") }
}
