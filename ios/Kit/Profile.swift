// A person's profile (profile.py): how they are reached, where they work, and, for a guardian looking at anyone, the details the emergency card
// and the school rules use. Readable and changeable by that person and by a guardian; the server refuses everyone else.
import Foundation

/// Where they work and when they usually start (HH:MM). The commute on Today is built from it, for them and for guardians only.
public struct ProfileWork: Codable, Hashable {
    public let place: String?
    public let lat: Double?
    public let lon: Double?
    public let starts: String?
}

public struct MemberProfile: Decodable, Hashable, Identifiable {
    public let id: UUID
    public let displayName: String
    public let role: String
    public let email: String?
    public let phone: String?
    public let dateOfBirth: Date?
    public let school: String?
    public let classLabel: String?
    public let allergies: String?
    public let bloodGroup: String?
    public let isMe: Bool
    /// Null for a child: a child has no work place.
    public let work: ProfileWork?
    /// Only on your own profile.
    public let telegramLinked: Bool?
    /// Only on your own profile, and not for a child: quiet hours, the daily cap and the morning message.
    public let reach: ReachPrefs?

    public var isChild: Bool { role == "child" }
}

/// A place the map search found: the words and the point, picked together.
public struct PlaceSuggestion: Decodable, Identifiable, Hashable {
    public let label: String
    public let lat: Double
    public let lon: Double
    public var id: String { "\(label)|\(lat)|\(lon)" }
}

public enum ProfileTime {
    /// "09:30" as a date today, for a time picker; nil when none is set or it cannot be read.
    public static func date(_ hhmm: String?) -> Date? {
        guard let hhmm, hhmm.count >= 5 else { return nil }
        let parts = hhmm.prefix(5).split(separator: ":")
        guard parts.count == 2, let h = Int(parts[0]), let m = Int(parts[1]) else { return nil }
        return Calendar.current.date(bySettingHour: h, minute: m, second: 0, of: Date())
    }

    /// A time picker's date as "HH:MM".
    public static func hhmm(_ date: Date) -> String {
        let c = Calendar.current.dateComponents([.hour, .minute], from: date)
        return String(format: "%02d:%02d", c.hour ?? 0, c.minute ?? 0)
    }
}

public enum BloodGroups {
    public static let all = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
}

extension API {
    public func memberProfile(_ id: UUID) async throws -> MemberProfile {
        try await json("GET", "/members/\(id.uuidString.lowercased())/profile")
    }

    /// Set or clear a work place and usual start. The place and its point come together; nil clears. The body is written by hand so a
    /// cleared field is an explicit null on the wire.
    public func setWork(_ id: UUID, place: PlaceSuggestion?, starts: String?) async throws -> MemberProfile {
        var body: [String: Any] = [:]
        body["label"] = place?.label ?? NSNull()
        body["lat"] = place?.lat ?? NSNull()
        body["lon"] = place?.lon ?? NSNull()
        body["starts"] = starts ?? NSNull()
        let data = try JSONSerialization.data(withJSONObject: body)
        let (out, _) = try await send("PUT", "/members/\(id.uuidString.lowercased())/work", body: data, contentType: "application/json")
        do { return try API.decoder.decode(MemberProfile.self, from: out) }
        catch { throw APIError(status: 0, detail: "The server's answer could not be read: \(error)") }
    }

    /// Allergies and blood group, for the emergency card. A guardian only.
    public func setMedical(_ id: UUID, allergies: String, bloodGroup: String) async throws {
        var body: [String: Any] = [:]
        body["allergies"] = allergies.isEmpty ? NSNull() : allergies
        body["blood_group"] = bloodGroup.isEmpty ? NSNull() : bloodGroup
        let data = try JSONSerialization.data(withJSONObject: body)
        _ = try await send("PUT", "/members/\(id.uuidString.lowercased())/medical", body: data, contentType: "application/json")
    }

    public func searchPlaces(_ text: String) async throws -> [PlaceSuggestion] {
        try await json("GET", "/places/search", query: ["q": text])
    }
}
