// WhatsApp reading from the phone: the chats a member names, read every half
// hour from their own linked WhatsApp Web (whatsapp_watch.py). The phone only
// controls it: it sets the number and the chats, shows the link code, and
// accepts the costs. Nothing here reads WhatsApp, and nothing is sent to it.
import Foundation

/// The model that reads what comes out of the chats, and where it runs.
public struct WhatsAppModel: Codable, Hashable {
    public let name: String
    public let trust: String
    public let `where`: String
    public var isHosted: Bool { trust == "cloud" }
}

/// A school the household's children are at, and who is there: what a chat can be said to belong to.
public struct WhatsAppSchool: Codable, Hashable, Identifiable {
    public let school: String
    public let children: [String]
    public var id: String { school }
    /// "Bright Start (Lily)": the school and who is at it.
    public var label: String { children.isEmpty ? school : "\(school) (\(children.joined(separator: ", ")))" }
}

/// One member's WhatsApp reading as the server describes it.
public struct WhatsAppStatus: Codable, Hashable {
    public let available: Bool
    public let hasPhone: Bool?
    /// Reading is on but what the person said yes to no longer covers where the words go (the notice model changed): the card offers "Resume".
    public let needsConsent: Bool?
    public let consent: [String]
    public let enabled: Bool
    public let status: String
    public let chats: [String]
    public let lastRunAt: Date?
    public let lastOkAt: Date?
    public let lastError: String?
    public let lastFound: Int?
    public let everyMinutes: Int?
    public let model: WhatsAppModel?
    /// Present while a link is waiting and WhatsApp offered a QR code instead of a code (base64 PNG).
    public let qr: String?
    /// The schools a chat can be tied to (absent for a child).
    public let schools: [WhatsAppSchool]?
    /// Chat name -> the school it belongs to. Set from the raw JSON after decoding: the phone's decoder rewrites dictionary keys with underscores.
    public var tags: [String: String]?
    /// Only on the answer to "stop and forget".
    public let note: String?

    public static let maxChats = 8

    public var phoneOnFile: Bool { hasPhone ?? false }
    public var consentPaused: Bool { enabled && (needsConsent ?? false) }
    /// Whether there is anything to choose: some chats saved, some school a child is at.
    public var canTagChats: Bool { !chats.isEmpty && !(schools ?? []).isEmpty }
    /// The school a chat was said to belong to, or nil for "nobody in particular".
    public func school(of chat: String) -> String? { tags?[chat] }
    public var linked: Bool { status == "linked" }
    public var lapsed: Bool { status == "lapsed" }
    public var minutes: Int { everyMinutes ?? 30 }

    /// What to say about the link, in words.
    public var linkWords: String {
        switch status {
        case "linked": return "Linked"
        case "lapsed": return "The link ended; link again"
        case "needs_link": return "Not linked yet"
        case "error": return "Could not read the last time"
        default: return "Not linked"
        }
    }
}

/// The code to type into WhatsApp, and how long the server's browser waits for it. `linked` is true when the profile was already linked.
public struct WhatsAppLink: Decodable {
    public let linked: Bool
    public let code: String?
    /// When WhatsApp gives no code the server falls back to the page's QR code: a base64 PNG, refreshed while the link waits.
    public let qr: String?
    public let expiresIn: Int?
}

/// What one "read now" pass did.
public struct WhatsAppPass: Decodable, Hashable {
    public let read: Int?
    public let taken: Int?
    public let missing: [String]?
    public let lapsed: Bool?
    public let failed: Bool?
    public let skipped: String?

    /// One plain line for the screen.
    public var words: String {
        if lapsed == true { return "WhatsApp asks to be linked again." }
        if failed == true { return "It could not read the chats this time." }
        if let skipped { return "Nothing to read: \(skipped)." }
        let found = taken ?? 0
        var line = found == 0 ? "Nothing new in the chats." : (found == 1 ? "1 new message went to your notices." : "\(found) new messages went to your notices.")
        if let missing, !missing.isEmpty { line += " Not found on your account: \(missing.joined(separator: ", "))." }
        return line
    }
}

/// The answer to "read now": what the pass did, with the status flattened beside it.
public struct WhatsAppReadNow: Decodable {
    public let result: WhatsAppPass?
    public let status: WhatsAppStatus

    private enum Keys: String, CodingKey { case result }
    public init(from decoder: Decoder) throws {
        result = try decoder.container(keyedBy: Keys.self).decodeIfPresent(WhatsAppPass.self, forKey: .result)
        status = try WhatsAppStatus(from: decoder)
    }
}

public enum WhatsAppChats {
    /// A chat per line, trimmed, blanks and repeats dropped.
    public static func parse(_ text: String) -> [String] {
        var seen = Set<String>()
        var out: [String] = []
        for line in text.split(whereSeparator: \.isNewline) {
            let name = line.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
            if !name.isEmpty, seen.insert(name.lowercased()).inserted { out.append(String(name.prefix(80))) }
        }
        return out
    }
}

extension API {
    public func whatsApp() async throws -> WhatsAppStatus {
        let (out, _) = try await send("GET", "/me/whatsapp")
        return try API.whatsAppStatus(from: out)
    }

    /// The status, with `tags` read from the raw JSON so a chat's name arrives exactly as the server holds it.
    static func whatsAppStatus(from data: Data) throws -> WhatsAppStatus {
        var status: WhatsAppStatus
        do { status = try API.decoder.decode(WhatsAppStatus.self, from: data) }
        catch { throw APIError(status: 0, detail: "The server's answer could not be read: \(error)") }
        if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let raw = obj["tags"] as? [String: String] { status.tags = raw }
        return status
    }

    /// The number WhatsApp knows this adult by, with its country code.
    public func setMyPhone(_ phone: String) async throws {
        struct Ignored: Decodable {}
        let _: Ignored = try await json("PUT", "/me/phone", body: ["phone": phone])
    }

    public func setWhatsAppChats(_ chats: [String]) async throws -> WhatsAppStatus {
        let body = try JSONSerialization.data(withJSONObject: ["chats": chats])
        let (out, _) = try await send("PUT", "/me/whatsapp/chats", body: body, contentType: "application/json")
        return try API.whatsAppStatus(from: out)
    }

    /// Say which school one chat belongs to ("" clears it). The body is written by hand because the phone's encoder would rewrite the
    /// chat's name, which is a dictionary key here. A guardian only; the server says why when a school is not one a child is at.
    public func tagWhatsAppChat(_ chat: String, school: String, chats: [String]) async throws -> WhatsAppStatus {
        let body = try JSONSerialization.data(withJSONObject: ["chats": chats, "tags": [chat: school]])
        let (out, _) = try await send("PUT", "/me/whatsapp/chats", body: body, contentType: "application/json")
        return try API.whatsAppStatus(from: out)
    }

    /// Starts linking; returns the code to type into WhatsApp. The server's browser waits for it for `expiresIn` seconds.
    public func startWhatsAppLink() async throws -> WhatsAppLink { try await json("POST", "/me/whatsapp/link") }

    /// Has the code been typed yet? Asked every few seconds while the code is on screen.
    public func whatsAppLinkStatus() async throws -> WhatsAppStatus {
        let (out, _) = try await send("GET", "/me/whatsapp/link")
        return try API.whatsAppStatus(from: out)
    }

    public func enableWhatsApp(understood: Bool, cloudOk: Bool) async throws -> WhatsAppStatus {
        let body = try API.encoder.encode(WhatsAppEnableBody(understood: understood, cloudOk: cloudOk))
        let (out, _) = try await send("POST", "/me/whatsapp/enable", body: body, contentType: "application/json")
        return try API.whatsAppStatus(from: out)
    }

    public func readWhatsAppNow() async throws -> WhatsAppReadNow { try await json("POST", "/me/whatsapp/read-now") }

    /// Stops, deletes the logged-in browser on the server's machine and the chat list. The answer carries the reminder to remove the device in WhatsApp.
    public func forgetWhatsApp() async throws -> WhatsAppStatus {
        let (out, _) = try await send("DELETE", "/me/whatsapp")
        return try API.whatsAppStatus(from: out)
    }
}

struct WhatsAppEnableBody: Encodable { let understood: Bool; let cloudOk: Bool }
