import SwiftUI
import AuthenticationServices

/// Server address, email, then the mailed link. The link works once and
/// expires in minutes, so the screen stays on the paste step until it is
/// redeemed or the person starts over.
struct SignInView: View {
    @EnvironmentObject var session: Session
    @State private var server = Server.baseURL?.absoluteString ?? ""
    @State private var email = Server.member?.email ?? ""
    @State private var link = ""
    @State private var sent = false
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Server") {
                    TextField("https://your-mac.your-tailnet.ts.net", text: $server)
                        .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                    Text("Where the console runs. On Tailscale today; a real host later.").font(.footnote).foregroundStyle(.secondary)
                }
                Section {
                    Button { Task { await google() } } label: { Label("Continue with Google", systemImage: "person.crop.circle") }
                        .disabled(busy || server.isEmpty)
                    Text("Signs in with the Google address the household knows. Nothing else is asked of Google.").font(.footnote).foregroundStyle(.secondary)
                }
                Section("Email") {
                    TextField("you@example.com", text: $email)
                        .keyboardType(.emailAddress).textInputAutocapitalization(.never).autocorrectionDisabled()
                    Button(sent ? "Send another link" : "Mail me a sign-in link") { Task { await request() } }
                        .disabled(busy || email.isEmpty || server.isEmpty)
                }
                if sent {
                    Section("The link from the mail") {
                        TextField("Paste the whole link here", text: $link, axis: .vertical)
                            .textInputAutocapitalization(.never).autocorrectionDisabled()
                        Button("Sign in") { Task { await redeem() } }.disabled(busy || link.isEmpty)
                        Text("It works once. Tapping it in Mail opens the console; long-press, copy, and paste it here.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                }
                if let error { Section { Text(error).foregroundStyle(.red) } }
            }
            .navigationTitle("FamilyOS")
            .task { if let value = session.pastedLink { await take(value) } }
            .onChange(of: session.signInNotice) { _, value in if let value { error = value } }
            .onChange(of: session.pastedLink) { _, value in
                if let value { Task { await take(value) } }
            }
        }
    }

    /// Google in a web session the system runs; it ends when Google's
    /// callback redirects to familyos://signed-in with the token.
    private func google() async {
        error = nil
        guard saveServer() else { return }
        busy = true; defer { busy = false }
        do {
            let url = try await API.shared.googleSignInURL()
            let back = try await WebAuth.run(url, scheme: Server.urlScheme)
            switch Session.googleOutcome(back) {
            case .token(let token)?: session.signedIn(try await API.shared.signIn(token: token))
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
        link = value; sent = true
        await redeem()
    }

    private func saveServer() -> Bool {
        var s = server.trimmingCharacters(in: .whitespacesAndNewlines)
        if !s.contains("://") { s = (s.hasPrefix("127.0.0.1") || s.hasPrefix("localhost") ? "http://" : "https://") + s }
        if s.hasSuffix("/") { s.removeLast() }
        guard let url = URL(string: s), url.host != nil else { error = "That is not a server address."; return false }
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
