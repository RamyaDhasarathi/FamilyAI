import SwiftUI
import AuthenticationServices

/// One calm screen: Continue with Google, or a mailed link. The server's address, which only matters while it sits on a private network,
/// waits under Advanced (and opens by itself when this build has none). A Google address no home uses turns the screen into "start your home".
struct SignInView: View {
    @EnvironmentObject var session: Session
    @State private var server = (Server.baseURL ?? Server.defaultURL)?.absoluteString ?? ""
    @State private var email = Server.member?.email ?? ""
    @State private var link = ""
    @State private var emailOpen = false
    @State private var advanced = Server.baseURL == nil && Server.defaultURL == nil
    @State private var sent = false
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        if let founding = session.founding {
            FoundingView(founding: founding)
        } else {
            signIn
        }
    }

    private var signIn: some View {
        ScrollView {
            VStack(spacing: Spacing.xl) {
                Spacer(minLength: Spacing.xxl)
                Image(systemName: "house.fill").font(.system(size: 34, weight: .medium)).foregroundStyle(Theme.primary)
                    .frame(width: 80, height: 80).background(Theme.primary.opacity(0.12)).clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
                    .accessibilityHidden(true)
                VStack(spacing: Spacing.s) {
                    Text("Hi, I'm FamilyOS").font(Theme.font(28, .regular, .serif)).foregroundStyle(Theme.ink)
                    Text("Your family's notices, dates and bills, read for you.").font(Theme.font(16)).foregroundStyle(Theme.ink2).multilineTextAlignment(.center)
                }
                VStack(spacing: Spacing.m) {
                    PrimaryButton(title: "Continue with Google") { Task { await google() } }
                        .disabled(busy || server.isEmpty)
                    GhostButton(title: emailOpen ? "Hide the email link" : "Email me a link") { withAnimation { emailOpen.toggle() } }
                    Text("Google shares your email address only. Reading mail is a separate choice, made later.")
                        .font(Theme.font(12)).foregroundStyle(Theme.ink3).multilineTextAlignment(.center)
                }
                if emailOpen { emailBlock }
                if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).multilineTextAlignment(.center) }
                DisclosureGroup("Advanced", isExpanded: $advanced) {
                    VStack(alignment: .leading, spacing: Spacing.s) {
                        TextField("https://your-host.example", text: $server)
                            .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                            .font(Theme.font(15)).padding(10).background(Theme.paper).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                            .accessibilityLabel("Server address")
                        Text("Where your household runs. Fresh builds are set to it already; on a private network it is the Tailscale address.")
                            .font(Theme.font(12)).foregroundStyle(Theme.ink3)
                    }.padding(.top, Spacing.s)
                }
                .font(Theme.font(14, .medium)).foregroundStyle(Theme.ink2).tint(Theme.ink3)
                Spacer(minLength: Spacing.xl)
            }
            .padding(.horizontal, Spacing.xl)
        }
        .scrollDismissesKeyboard(.interactively)
        .paper()
        .task { if let value = session.pastedLink { await take(value) } }
        .onChange(of: session.signInNotice) { _, value in if let value { error = value } }
        .onChange(of: session.pastedLink) { _, value in
            if let value { Task { await take(value) } }
        }
    }

    private var emailBlock: some View {
        VStack(alignment: .leading, spacing: Spacing.m) {
            TextField("you@example.com", text: $email)
                .keyboardType(.emailAddress).textInputAutocapitalization(.never).autocorrectionDisabled()
                .font(Theme.font(15)).padding(12).background(Theme.paper).overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(Theme.line))
                .accessibilityLabel("Your email address")
            Button(sent ? "Send another link" : "Mail me a sign-in link") { Task { await request() } }
                .font(Theme.font(15, .semibold)).foregroundStyle(Theme.primary).disabled(busy || email.isEmpty || server.isEmpty)
            if sent {
                TextField("Paste the whole link here", text: $link, axis: .vertical)
                    .textInputAutocapitalization(.never).autocorrectionDisabled()
                    .font(Theme.font(15)).padding(12).background(Theme.paper).overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(Theme.line))
                Button("Sign in") { Task { await redeem() } }.font(Theme.font(15, .semibold)).foregroundStyle(Theme.primary).disabled(busy || link.isEmpty)
                Text("It works once. Tapping it in Mail opens the console; long-press, copy, and paste it here.")
                    .font(Theme.font(12)).foregroundStyle(Theme.ink3)
            }
        }
        .padding(Spacing.l).background(Theme.primaryTint.opacity(0.5)).clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    /// Google in a web session the system runs; it ends when Google's
    /// callback redirects to familyos://signed-in with the token.
    private func google() async {
        error = nil
        guard saveServer() else { return }
        busy = true; session.signInInFlight = true; defer { busy = false; session.signInInFlight = false }
        do {
            let url = try await API.shared.googleSignInURL()
            let back = try await WebAuth.run(url, scheme: Server.urlScheme)
            switch Session.googleOutcome(back) {
            case .token(let token)?: session.signedIn(try await API.shared.signIn(token: token))
            case .new(let email, let ticket)?: session.founding = Session.Founding(email: email, ticket: ticket)
            case .notice(let text)?: error = text
            case nil: error = "Google came back somewhere unexpected."
            }
        } catch let e as ASWebAuthenticationSessionError where e.code == .canceledLogin {
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    /// A link that arrived whole, from the URL scheme or a launch argument.
    private func take(_ value: String) async {
        if let base = Server.baseURL { server = base.absoluteString }
        link = value; sent = true; emailOpen = true
        await redeem()
    }

    private func saveServer() -> Bool {
        var s = server.trimmingCharacters(in: .whitespacesAndNewlines)
        if !s.contains("://") { s = (s.hasPrefix("127.0.0.1") || s.hasPrefix("localhost") ? "http://" : "https://") + s }
        if s.hasSuffix("/") { s.removeLast() }
        guard let url = URL(string: s), url.host != nil else { error = "That is not a server address."; advanced = true; return false }
        Server.baseURL = url
        return true
    }

    private func request() async {
        error = nil
        guard saveServer() else { return }
        busy = true; defer { busy = false }
        do { try await API.shared.requestSignIn(email: email.trimmingCharacters(in: .whitespaces)); sent = true }
        catch { self.error = error.localizedDescription }
    }

    private func redeem() async {
        error = nil
        guard saveServer() else { return }
        guard let raw = Server.signInLink(from: link) else { error = "No link in what was pasted."; return }
        busy = true; defer { busy = false }
        do {
            let signed = try await API.shared.redeem(link: raw)
            session.signedIn(signed)
        } catch { self.error = error.localizedDescription }
    }
}

/// Google vouched for an address no household uses. Two questions, and the home exists: the first guardian is whoever just signed in.
struct FoundingView: View {
    @EnvironmentObject var session: Session
    let founding: Session.Founding
    @State private var myName = ""
    @State private var homeName = ""
    @State private var busy = false
    @State private var error: String?
    @FocusState private var focus: Field?
    private enum Field { case me, home }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.xl) {
                Spacer(minLength: Spacing.xl)
                VStack(alignment: .leading, spacing: Spacing.s) {
                    Text("Let's start your home").font(Theme.font(28, .regular, .serif)).foregroundStyle(Theme.ink)
                    Text("No home uses \(founding.email) yet, so this one will be yours. First names are all I need.")
                        .font(Theme.font(16)).foregroundStyle(Theme.ink2)
                }
                VStack(alignment: .leading, spacing: Spacing.m) {
                    label("What should I call you?")
                    TextField("Your first name", text: $myName).textInputAutocapitalization(.words).focused($focus, equals: .me).submitLabel(.next)
                        .onSubmit { focus = .home }.modifier(FirstRunField())
                    label("What is your family called?")
                    TextField(suggestion, text: $homeName).textInputAutocapitalization(.words).focused($focus, equals: .home).submitLabel(.go)
                        .onSubmit { Task { await create() } }.modifier(FirstRunField())
                }
                if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger) }
                PrimaryButton(title: busy ? "Starting…" : "Start my home") { Task { await create() } }
                    .disabled(busy || myName.trimmingCharacters(in: .whitespaces).isEmpty)
                Button("Use a different account") { session.founding = nil }
                    .font(Theme.font(15, .medium)).foregroundStyle(Theme.ink3).frame(maxWidth: .infinity)
            }
            .padding(.horizontal, Spacing.xl)
        }
        .scrollDismissesKeyboard(.interactively)
        .paper()
    }

    private var suggestion: String {
        let n = myName.trimmingCharacters(in: .whitespaces)
        return n.isEmpty ? "The Rao family" : "The \(n) family"
    }

    private func label(_ text: String) -> some View { Text(text).font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink) }

    private func create() async {
        let me = myName.trimmingCharacters(in: .whitespaces)
        guard !me.isEmpty, !busy else { return }
        let home = homeName.trimmingCharacters(in: .whitespaces)
        busy = true; error = nil; defer { busy = false }
        do {
            let created = try await API.shared.foundHousehold(name: home.isEmpty ? suggestion : home, guardianName: me, email: founding.email, ticket: founding.ticket)
            session.founded(created)
        } catch { self.error = error.localizedDescription }
    }
}

#Preview("Sign in") { SignInView().environmentObject(Session()) }
#Preview("Start a home") { FoundingView(founding: .init(email: "asha@example.com", ticket: "fnd_preview")).environmentObject(Session()) }

/// ASWebAuthenticationSession as one async call.
enum WebAuth {
    @MainActor
    static func run(_ url: URL, scheme: String) async throws -> URL {
        let anchor = Anchor()
        return try await withCheckedThrowingContinuation { cont in
            let session = ASWebAuthenticationSession(url: url, callbackURLScheme: scheme) { back, err in
                if let back { cont.resume(returning: back) } else { cont.resume(throwing: err ?? APIError(status: 0, detail: "Sign-in ended without an answer.")) }
            }
            session.presentationContextProvider = anchor
            session.prefersEphemeralWebBrowserSession = false
            anchor.session = session
            if !session.start() { cont.resume(throwing: APIError(status: 0, detail: "The sign-in window could not open.")) }
        }
    }

    final class Anchor: NSObject, ASWebAuthenticationPresentationContextProviding {
        var session: ASWebAuthenticationSession?
        func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
            UIApplication.shared.connectedScenes.compactMap { ($0 as? UIWindowScene)?.keyWindow }.first ?? ASPresentationAnchor()
        }
    }
}
