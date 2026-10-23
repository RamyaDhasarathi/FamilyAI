// Where the server is and who is signed in, kept where both the app and
// the share extension can read them: the address and the member in the
// app group's defaults, the tokens in the Keychain under the app group.
import Foundation
import Security

public enum Server {
    public static let appGroup = "group.com.arunmozhi.familyos"
    public static let urlScheme = "familyos"

    static let defaults = UserDefaults(suiteName: appGroup) ?? .standard

    public static var baseURL: URL? {
        get { defaults.string(forKey: "base_url").flatMap(URL.init(string:)) }
        set { defaults.set(newValue?.absoluteString, forKey: "base_url") }
    }

    public static var member: Member? {
        get { defaults.data(forKey: "member").flatMap { try? API.decoder.decode(Member.self, from: $0) } }
        set { defaults.set(newValue.flatMap { try? API.encoder.encode($0) }, forKey: "member") }
    }

    /// The household's members, for the tag picker in the share sheet.
    public static var members: [Member] {
        get { defaults.data(forKey: "members").flatMap { try? API.decoder.decode([Member].self, from: $0) } ?? [] }
        set { defaults.set(try? API.encoder.encode(newValue), forKey: "members") }
    }

    /// The session token: this phone's sign-in.
    public static var token: String? {
        get { Keychain.read("session") }
        set { Keychain.write("session", newValue) }
    }

    /// A device token for the share extension, issued at sign-in; shown on the
    /// console's Devices card and revocable there without signing the app out.
    public static var deviceToken: String? {
        get { Keychain.read("device") }
        set { Keychain.write("device", newValue) }
    }

    /// The device token's own id, so a fresh sign-in can revoke the one it
    /// replaces instead of leaving it on the Devices card as "not used yet".
    public static var deviceId: String? {
        get { Keychain.read("device-id") }
        set { Keychain.write("device-id", newValue) }
    }

    public static var isSignedIn: Bool { baseURL != nil && token != nil && member != nil }

    public static func forget() {
        token = nil
        deviceToken = nil
        deviceId = nil
        member = nil
        members = []
    }

    /// Takes the one-time link out of whatever was pasted: the whole mailed
    /// URL, a `familyos://signin?link=…` URL, or the bare link itself.
    public static func signInLink(from text: String) -> String? {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if t.isEmpty { return nil }
        if let url = URL(string: t), let comps = URLComponents(url: url, resolvingAgainstBaseURL: false),
           let link = comps.queryItems?.first(where: { $0.name == "link" })?.value, !link.isEmpty {
            return link
        }
        if t.contains("://") { return nil }
        return t
    }
}

enum Keychain {
    static let service = "com.arunmozhi.familyos"

    /// Under the app group when the build is entitled to it (a signed build
    /// on a phone, so the extension sees the same item), and without the
    /// group otherwise (an unsigned simulator build). Each read tries both.
    static func read(_ account: String) -> String? {
        for grouped in [true, false] {
            var query = base(account, grouped: grouped)
            query[kSecReturnData as String] = true
            query[kSecMatchLimit as String] = kSecMatchLimitOne
            var out: AnyObject?
            let status = SecItemCopyMatching(query as CFDictionary, &out)
            if status == errSecSuccess, let data = out as? Data {
                return String(data: data, encoding: .utf8)
            }
            NSLog("familyos keychain read %@ grouped=%d status=%d", account, grouped ? 1 : 0, status)
        }
        return nil
    }

    static func write(_ account: String, _ value: String?) {
        for grouped in [true, false] { SecItemDelete(base(account, grouped: grouped) as CFDictionary) }
        guard let value, let data = value.data(using: .utf8) else { return }
        for grouped in [true, false] {
            var query = base(account, grouped: grouped)
            query[kSecValueData as String] = data
            query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
            let status = SecItemAdd(query as CFDictionary, nil)
            if status == errSecSuccess { return }
            NSLog("familyos keychain write %@ grouped=%d status=%d", account, grouped ? 1 : 0, status)
        }
    }

    private static func base(_ account: String, grouped: Bool) -> [String: Any] {
        var q: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                kSecAttrService as String: service,
                                kSecAttrAccount as String: account]
        if grouped { q[kSecAttrAccessGroup as String] = Server.appGroup }
        return q
    }
}
