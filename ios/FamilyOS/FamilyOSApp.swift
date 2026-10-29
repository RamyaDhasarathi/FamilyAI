import SwiftUI

@main
struct FamilyOSApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var session = Session()
    @ObservedObject private var reminders = ReminderCenter.shared
    @Environment(\.scenePhase) private var phase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(session)
                .onOpenURL { url in session.open(url) }
                .task { await session.flushOutbox(); await liveSync(); await reminders.sync(); await HealthCenter.shared.refresh() }
                .onChange(of: phase) { _, now in
                    if now == .active { Task { await session.flushOutbox(); await liveSync(); await reminders.sync(); await HealthCenter.shared.refresh() } }
                    else if now == .background, reminders.enabled { ReminderCenter.scheduleRefresh() }
                }
                .sheet(item: Binding(get: { reminders.opened.map(OpenedNotice.init) }, set: { _ in reminders.opened = nil })) { o in
                    NavigationStack { NoticeView(artifactId: o.id, title: "Reminder") }.environmentObject(session)
                }
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
    /// A Google-verified address that has no household yet, and the ticket to found one: the sign-in screen turns into "start your home".
    @Published var founding: Founding?
    /// The first-run screens, shown over the app until they are finished or put away.
    @Published var firstRun: FirstRunStart?
    /// Set by the founding screen so the first run opens at the family, the home having just been named.
    private var justFounded = false
    /// True while our own ASWebAuthenticationSession for Google sign-in is open.
    var signInInFlight = false
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

    struct Founding: Equatable { let email: String; let ticket: String }
    enum FirstRunStart { case name, family }

    /// A home founded from this phone: signed in as its first guardian, with the name already given.
    func founded(_ created: HouseholdCreated) {
        justFounded = true
        founding = nil
        signedIn(created.credentials)
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
        await openFirstRunIfDue()
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

    /// A brand-new home goes through the first-run screens once. The server says so (`wizard`) until the name step is answered.
    private func openFirstRunIfDue() async {
        if justFounded {
            justFounded = false
            _ = try? await API.shared.answerOnboarding("named")
            firstRun = .family
        } else if firstRun == nil, let o = try? await API.shared.onboarding(), o.wizard == true {
            firstRun = .name
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
        HealthCenter.shared.reset()      // stop listening and forget the switch: the next person's phone state is their own
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
            case .token(let token):
                // Only while a sign-in of ours is in flight and nobody is signed in: any app or web page can open this URL.
                guard !isSignedIn, signInInFlight else { return }
                Task { if let s = try? await API.shared.signIn(token: token) { self.signedIn(s) } }
            case .notice(let text): signInNotice = text
            case .new(let email, let ticket):
                guard !isSignedIn, signInInFlight else { return }
                founding = Founding(email: email, ticket: ticket)
            }
            return
        }
        guard let link = Server.signInLink(from: url.absoluteString) else { return }
        // A link in a web page or another app must not repoint a signed-in phone at another server: that would send
        // the session token there. Signed out, the server is only offered; SignInView shows it and waits for a tap.
        if !isSignedIn,
           let s = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "server" })?.value,
           let base = URL(string: s), base.scheme == "https", base.host != nil {
            Server.baseURL = base
        }
        guard !isSignedIn else { return }
        pastedLink = link
    }

    enum GoogleOutcome { case token(String), notice(String), new(email: String, ticket: String) }

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
            // Google vouched for an address no household uses: the fragment carries it and the one-use ticket to found a home with it.
            func piece(_ name: String) -> String? {
                (comps?.fragment ?? "").split(separator: "&").compactMap { $0.hasPrefix(name + "=") ? String($0.dropFirst(name.count + 1)).removingPercentEncoding : nil }.first
            }
            guard let email = piece("email"), let ticket = piece("found"), !ticket.isEmpty else { return .notice("Google did not say which address to start a home with. Try again.") }
            return .new(email: email, ticket: ticket)
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

/// A notice opened from a banner.
struct OpenedNotice: Identifiable { let id: UUID }
