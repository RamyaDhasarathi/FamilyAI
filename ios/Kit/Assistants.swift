// The person's own assistants and what FamilyOS was taught, as the app reads
// them: instructions sent to their own Claude or Grok (assistant_tasks.py),
// outside MCP servers they allow (mcp_client.py), keys an assistant connects
// with (agents.py), and skills kept from a demonstration (taught.py).
// Keys and credentials go to the server once and are never kept here.
import Foundation

// MARK: ask my assistant

public struct AssistantConnection: Decodable, Identifiable, Hashable {
    public let id: UUID
    public let provider: String
    public let label: String
    public let model: String?
    public let dailyCap: Int
    public let usedToday: Int
}

public struct AssistantTask: Decodable, Identifiable, Hashable {
    public let id: UUID
    public let instruction: String
    /// queued, running, done or failed.
    public let status: String
    public let result: String?
    public let error: String?
    public let label: String
    public let createdAt: Date
    public let completedAt: Date?

    public var isLive: Bool { status == "queued" || status == "running" }
}

// MARK: outside servers

public struct McpServer: Decodable, Identifiable, Hashable {
    public let id: UUID
    public let label: String
    public let url: String
    public let allowedTools: [String]
    public let hasCredential: Bool
}

/// The server's tools: names and descriptions from a stranger, to choose from.
public struct McpTools: Decodable {
    public struct Tool: Decodable, Identifiable, Hashable { public let name: String; public let description: String; public let allowed: Bool; public var id: String { name } }
    public let tools: [Tool]
    public let notice: String
}

/// What one call brought back: untrusted text, not stored.
public struct McpCallResult: Decodable {
    public let ok: Bool
    public let text: String?
    public let error: String?
    public let addressedToModels: Bool?
    public let notice: String
}

// MARK: connect my assistant

public struct AgentKey: Decodable, Identifiable, Hashable {
    public let id: UUID
    public let label: String
    public let canShare: Bool
    public let expiresAt: Date
    public let revokedAt: Date?
    public let calls7D: Int
    public let active: Bool
}

/// A new key, shown once.
public struct AgentIssued: Decodable {
    public let id: UUID
    public let label: String
    public let token: String
    public let canShare: Bool
    public let expiresAt: Date
    public let can: [String]
}

// MARK: what FamilyOS was taught

public struct TaughtSkill: Decodable, Identifiable, Hashable {
    public struct Step: Decodable, Hashable { public let op: String; public let text: String?; public let direction: String? }
    public let id: UUID
    public let title: String
    /// phone or web.
    public let kind: String
    public let target: String
    public let steps: [Step]
    public let runs: Int
    public let lastRunAt: Date?
    public let lastOutcome: String?

    public var isWeb: Bool { kind == "web" }
}

public struct SkillRun: Decodable {
    /// done, or needs_you with where it stopped.
    public let status: String
    public let handedIn: Int
    public let stopped: String?
}

extension API {
    private func idPath(_ base: String, _ id: UUID, _ tail: String = "") -> String { "\(base)/\(id.uuidString.lowercased())\(tail)" }

    // ask my assistant
    public func assistantConnections() async throws -> [AssistantConnection] { try await json("GET", "/me/assistant-connections") }
    /// The key is sent once, sealed on the server and never returned.
    public func addAssistantConnection(provider: String, label: String, apiKey: String, model: String, dailyCap: Int) async throws {
        struct Body: Encodable { let provider: String; let label: String; let apiKey: String; let model: String; let dailyCap: Int }
        struct R: Decodable { let id: UUID }
        let _: R = try await json("POST", "/me/assistant-connections", body: Body(provider: provider, label: label, apiKey: apiKey, model: model, dailyCap: dailyCap))
    }
    public func removeAssistantConnection(_ id: UUID) async throws { _ = try await send("DELETE", idPath("/me/assistant-connections", id)) }
    public func assistantTasks() async throws -> [AssistantTask] { try await json("GET", "/me/assistant-tasks") }
    public func assistantTask(_ id: UUID) async throws -> AssistantTask { try await json("GET", idPath("/me/assistant-tasks", id)) }
    public func sendAssistantTask(connection: UUID, instruction: String) async throws -> UUID {
        struct Body: Encodable { let connectionId: UUID; let instruction: String }
        struct R: Decodable { let id: UUID; let status: String }
        let r: R = try await json("POST", "/me/assistant-tasks", body: Body(connectionId: connection, instruction: instruction))
        return r.id
    }

    // outside servers
    public func mcpServers() async throws -> [McpServer] { try await json("GET", "/me/mcp-servers") }
    public func addMcpServer(label: String, url: String, auth: String) async throws -> McpServer {
        try await json("POST", "/me/mcp-servers", body: ["label": label, "url": url, "auth": auth])
    }
    public func removeMcpServer(_ id: UUID) async throws { _ = try await send("DELETE", idPath("/me/mcp-servers", id)) }
    public func mcpTools(_ id: UUID) async throws -> McpTools { try await json("GET", idPath("/me/mcp-servers", id, "/tools")) }
    public func allowMcpTools(_ id: UUID, tools: [String]) async throws -> McpServer {
        try await json("PUT", idPath("/me/mcp-servers", id, "/allowed"), body: ["tools": tools])
    }
    /// Arguments as the person wrote them, already parsed from JSON.
    public func callMcpTool(_ id: UUID, tool: String, arguments: [String: Any]) async throws -> McpCallResult {
        let body = try JSONSerialization.data(withJSONObject: ["tool": tool, "arguments": arguments])
        let (out, _) = try await send("POST", idPath("/me/mcp-servers", id, "/call"), body: body, contentType: "application/json")
        do { return try API.decoder.decode(McpCallResult.self, from: out) }
        catch { throw APIError(status: 0, detail: "The server's answer could not be read: \(error)") }
    }

    // connect my assistant
    public func agentKeys() async throws -> [AgentKey] { try await json("GET", "/me/agents") }
    public func connectAgent(label: String, canShare: Bool, days: Int) async throws -> AgentIssued {
        struct Body: Encodable { let label: String; let canShare: Bool; let days: Int }
        return try await json("POST", "/me/agents", body: Body(label: label, canShare: canShare, days: days))
    }
    public func disconnectAgent(_ id: UUID) async throws { _ = try await send("DELETE", idPath("/me/agents", id)) }
    /// Where an assistant connects: this server's /mcp.
    public var agentAddress: String? { Server.baseURL?.appendingPathComponent("mcp").absoluteString }

    // what FamilyOS was taught
    public func skills() async throws -> [TaughtSkill] { try await json("GET", "/me/skills") }
    public func forgetSkill(_ id: UUID) async throws { _ = try await send("DELETE", idPath("/me/skills", id)) }
    /// Web skills only; a phone skill runs when the phone driver connects from the Mac.
    public func runSkill(_ id: UUID) async throws -> SkillRun { try await json("POST", idPath("/me/skills", id, "/run")) }
}
