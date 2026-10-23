import SwiftUI

@main
struct FamilyOSApp: App {
    @StateObject private var session = Session()
    @Environment(\.scenePhase) private var phase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(session)
                .onOpenURL { url in session.open(url) }
                .task { await session.flushOutbox(); await liveSync() }
                .onChange(of: phase) { _, now in if now == .active { Task { await session.flushOutbox(); await liveSync() } } }
        }
    }
}

@MainActor
private func liveSync() async {
    #if canImport(ActivityKit)
    if Server.token != nil { await LiveActivities.refresh() }
    #endif
}

/// Who is signed in, for every screen. Reads the app group on launch so a
/// sign-in survives the app being closed; a sign-out forgets it everywhere,
/// including the share extension.
@MainActor
final class Session: ObservableObject {
    @Published var member: Member? = Server.member
    @Published var members: [Member] = Server.members
    @Published var pastedLink: String?
    /// The device token a fresh sign-in is replacing, revoked after it.
    private var replacedDevice: String?

    var isSignedIn: Bool { member != nil && Server.token != nil && Server.baseURL != nil }

    init() {
        #if DEBUG
        // A debug build launched with `-signinLink <link> -server <url>` signs
        // in without the share sheet or the paste step: how the simulator is
        // driven from a script. Never in a release build.
        let d = UserDefaults.standard
        if let link = d.string(forKey: "signinLink"), !link.isEmpty {
            replacedDevice = Server.deviceId   // revoked once the new sign-in has a token of its own
            Server.forget(); member = nil; members = []
            if let s = d.string(forKey: "server"), let base = URL(string: s), base.host != nil { Server.baseURL = base }
            pastedLink = link
        }
        #endif
    }

    func signedIn(_ signed: SignedIn) {
        Server.token = signed.token
        Server.member = signed.member
        member = signed.member
        // Publishing the member swaps the sign-in screen out, which cancels
        // any task that screen started; the follow-ups run on their own.
        Task { await self.afterSignIn() }
    }

    private func afterSignIn() async {
        await refreshHousehold()
        // The extension's own token, so it shows on the Devices card and can be
        // revoked without signing the app out. Best effort: the session token
        // stands in if it cannot be issued.
        if Server.deviceToken == nil, let issued = try? await API.shared.addDevice(label: "iPhone app") {
            Server.deviceToken = issued.token
            Server.deviceId = issued.device.id.uuidString
        }
        if let old = replacedDevice, let id = UUID(uuidString: old), id.uuidString != Server.deviceId {
            try? await API.shared.revokeDevice(id)
            replacedDevice = nil
        }
    }

    func refreshHousehold() async {
        if let h = try? await API.shared.household() {
            Server.members = h.members
            members = h.members
        }
    }

    func signOut() async {
        try? await API.shared.signOut()
        Server.forget()
        member = nil
        members = []
    }

    /// What Google's callback said when it came back on the scheme outside
    /// the web session (a browser that opened the link itself).
    @Published var signInNotice: String?

    /// familyos://signin?link=…&server=… from a mail client that knows the
    /// scheme (the server rides along so one link is the whole sign-in), or
    /// familyos://signed-in#token=… from the Google callback.
    func open(_ url: URL) {
        guard url.scheme == Server.urlScheme else { return }
        if let outcome = Session.googleOutcome(url) {
            switch outcome {
            case .token(let token): Task { if let s = try? await API.shared.signIn(token: token) { self.signedIn(s) } }
            case .notice(let text): signInNotice = text
            }
            return
        }
        guard let link = Server.signInLink(from: url.absoluteString) else { return }
        if let s = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "server" })?.value,
           let base = URL(string: s), base.host != nil {
            Server.baseURL = base
        }
        pastedLink = link
    }

    enum GoogleOutcome { case token(String), notice(String) }

    /// familyos://signed-in#token=… is a sign-in; familyos://signin?signin=…
    /// says why there was none.
    static func googleOutcome(_ url: URL) -> GoogleOutcome? {
        let comps = URLComponents(url: url, resolvingAgainstBaseURL: false)
        if url.host == "signed-in" || url.path.hasPrefix("/signed-in") {
            let frag = comps?.fragment ?? ""
            for pair in frag.split(separator: "&") {
                let kv = pair.split(separator: "=", maxSplits: 1).map(String.init)
                if kv.count == 2, kv[0] == "token", let token = kv[1].removingPercentEncoding, !token.isEmpty { return .token(token) }
            }
            return .notice("Google came back without a token. Try again.")
        }
        guard let why = comps?.queryItems?.first(where: { $0.name == "signin" })?.value else { return nil }
        switch why {
        case "new":
            let email = (comps?.fragment ?? "").split(separator: "&").compactMap { $0.hasPrefix("email=") ? String($0.dropFirst(6)).removingPercentEncoding : nil }.first
            return .notice("No household uses \(email ?? "that address") yet. Start one on the console, then sign in here.")
        case "cancelled": return .notice("Google sign-in was cancelled.")
        case "failed": return .notice("Google sign-in did not go through. Try again.")
        default: return nil
        }
    }

    /// What the phone kept while it had no signal, and whether anything is still waiting.
    @Published var outboxLeft = Outbox.pending().count

    func flushOutbox() async {
        guard isSignedIn else { return }
        let result = await Outbox.replay()
        outboxLeft = result.left
    }

    /// Do a thing now, or keep it for later when the server cannot be reached.
    func doOrKeep(label: String, keep: () -> Void, _ work: () async throws -> Void) async -> String? {
        do { try await work(); return nil }
        catch {
            if Outbox.isTransient(error) { keep(); outboxLeft = Outbox.pending().count; return "No signal. \(label) is kept and will be sent when the phone is back online." }
            return error.localizedDescription
        }
    }

    func name(of id: UUID?) -> String? {
        guard let id else { return nil }
        return members.first { $0.id == id }?.displayName
    }
}
