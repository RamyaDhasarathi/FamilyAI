import SwiftUI

/// The first-run checklist on Today: sign in, name the home, add the family,
/// a channel, a mailbox, make it private. Shown only while the server says so (a guardian with
/// something left who has not hidden it). Each step reads off the household;
/// a button either answers the step or goes to the place it is done.
struct SetupChecklistCard: View {
    /// Goes to where the family is added. Without one, Settings opens.
    var onFamily: (() -> Void)?
    /// Goes to where the family key is set up. Without one, Settings opens.
    var onPrivate: (() -> Void)?
    /// Space above the card, given only when the card shows, so a hidden checklist leaves no gap.
    var spacingAbove: CGFloat = 0
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var status: SetupStatus?
    @State private var busy = false
    @State private var error: String?
    @State private var answered = 0
    private let sample: SetupStatus?

    init(onFamily: (() -> Void)? = nil, onPrivate: (() -> Void)? = nil, spacingAbove: CGFloat = 0, sample: SetupStatus? = nil) {
        self.onFamily = onFamily; self.onPrivate = onPrivate; self.spacingAbove = spacingAbove; self.sample = sample
    }

    var body: some View {
        VStack(spacing: 0) {
            Color.clear.frame(height: 0).accessibilityHidden(true)
            if let s = status, s.show { card(s).padding(.top, spacingAbove).transition(.opacity) }
        }
        .sensoryFeedback(.success, trigger: answered)
        .task {
            if let sample { status = sample; return }
            status = try? await API.shared.onboarding()
        }
    }

    private func answer(_ choice: String) async {
        busy = true
        defer { busy = false }
        do {
            let next = try await API.shared.answerOnboarding(choice)
            withAnimation(Motion.gentle(reduceMotion)) { status = next }
            error = nil; answered += 1
        } catch { self.error = error.localizedDescription }
    }

    /// Google in the app's web session, then the mailbox is finished here; the card reads the answer straight after.
    private func connectMail() async {
        do {
            if try await MailConnect.run() { status = try? await API.shared.onboarding() ?? status; answered += 1 }
            error = nil
        } catch let e as APIError where e.status == 503 { error = "Mail is not set up on this server." }
        catch { self.error = error.localizedDescription }
    }

    /// Opens the bot with this account's one-time link; the card reads the answer the next time Today opens.
    private func linkTelegram() async {
        do {
            let link = try await API.shared.telegramLink()
            if let url = URL(string: link.url) { await UIApplication.shared.open(url) }
            error = nil
        } catch let e as APIError where e.status == 503 { error = "Telegram is not set up on this server." }
        catch { self.error = error.localizedDescription }
    }

    private func card(_ s: SetupStatus) -> some View {
        Card {
            VStack(alignment: .leading, spacing: Spacing.m) {
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Set up your home").font(Theme.font(17, .semibold)).foregroundStyle(Theme.ink)
                        Text("\(s.done) of \(s.total) done").font(Theme.font(13)).foregroundStyle(Theme.ink3)
                    }
                    .accessibilityElement(children: .combine).accessibilityAddTraits(.isHeader)
                    Spacer()
                    Button("Hide") { Task { await answer("dismissed") } }
                        .font(Theme.font(14, .medium)).foregroundStyle(Theme.ink3).frame(minWidth: 44, minHeight: 44)
                        .accessibilityLabel("Hide the setup checklist")
                }
                ProgressView(value: Double(s.done), total: Double(max(s.total, 1))).tint(Theme.primary).accessibilityHidden(true)
                ForEach(s.steps) { step in row(step) }
                if let error { Text(error).font(Theme.font(12)).foregroundStyle(Theme.danger) }
            }
        }
        .opacity(busy ? 0.6 : 1)
        .disabled(busy)
    }

    private func row(_ step: SetupStep) -> some View {
        HStack(alignment: .top, spacing: Spacing.m) {
            Image(systemName: step.done ? "checkmark.circle.fill" : "circle")
                .font(Theme.font(20)).foregroundStyle(step.done ? Theme.success : Theme.ink3)
                .accessibilityLabel(step.done ? "Done" : step.optional ? "Can wait" : "To do")
            VStack(alignment: .leading, spacing: Spacing.xs) {
                Text(step.title).font(Theme.font(15, .medium)).foregroundStyle(step.done ? Theme.ink3 : Theme.ink)
                if let detail = step.detail, !detail.isEmpty, !step.done || step.key == "named" {
                    Text(step.key == "named" ? "“\(detail)”" : detail).font(Theme.font(12)).foregroundStyle(Theme.ink3)
                }
                if !step.done { buttons(step) }
            }
            Spacer(minLength: 0)
        }
        .accessibilityElement(children: .contain)
    }

    @ViewBuilder private func buttons(_ step: SetupStep) -> some View {
        switch step.key {
        case "named":
            Button { Task { await answer("named") } } label: { pill("Looks right", primary: true) }.buttonStyle(.plain)
        case "family":
            go(onFamily) { pill("Add your family", primary: true) }
        case "channel":
            HStack(spacing: Spacing.s) {
                Button { Task { await linkTelegram() } } label: { pill("Link Telegram", primary: true) }.buttonStyle(.plain)
                Button { Task { await answer("skip_channel") } } label: { pill("Later", primary: false) }
                    .buttonStyle(.plain).accessibilityLabel("Link Telegram later")
            }
        case "mail":
            HStack(spacing: Spacing.s) {
                Button { Task { await connectMail() } } label: { pill("Connect Google", primary: true) }.buttonStyle(.plain)
                Button { Task { await answer("skip_mail") } } label: { pill("Later", primary: false) }
                    .buttonStyle(.plain).accessibilityLabel("Connect mail later")
            }
        case "private":
            HStack(spacing: Spacing.s) {
                go(onPrivate) { pill("Make it private", primary: true) }
                Button { Task { await answer("skip_private") } } label: { pill("Later", primary: false) }
                    .buttonStyle(.plain).accessibilityLabel("Make it private later")
            }
        default:
            EmptyView()
        }
    }

    /// The caller's way there, or Settings through the stack's own destination.
    @ViewBuilder private func go<L: View>(_ action: (() -> Void)?, @ViewBuilder label: () -> L) -> some View {
        if let action { Button(action: action, label: label).buttonStyle(.plain) }
        else { NavigationLink(value: "settings", label: label).buttonStyle(.plain) }
    }

    private func pill(_ title: String, primary: Bool) -> some View {
        Text(title).font(Theme.font(14, primary ? .semibold : .medium)).foregroundStyle(primary ? .white : Theme.ink)
            .padding(.horizontal, 14).frame(minHeight: 36)
            .background(primary ? Theme.primary : Theme.card)
            .overlay(Capsule().stroke(primary ? .clear : Theme.line, lineWidth: 1))
            .clipShape(Capsule()).contentShape(Capsule())
            .padding(.top, 2)
    }
}

extension PreviewData {
    static let setup: SetupStatus = decode("""
    {"steps":[
      {"key":"signed_in","title":"You are signed in","detail":"Your own sign-in, nobody else’s.","done":true,"optional":false},
      {"key":"named","title":"Name your home","detail":"The Alex home","done":false,"optional":false},
      {"key":"family","title":"Add your family","detail":"Invite the adults with a link; add the children.","done":false,"optional":false},
      {"key":"channel","title":"Message it from your phone","detail":"Link Telegram once; the day's brief and your replies go there.","done":false,"optional":true,"on":false},
      {"key":"mail","title":"Connect your mail and calendar","detail":"Read-only to start. Sending is a separate choice, made later.","done":false,"optional":true,"on":false},
      {"key":"private","title":"Make it private to your family","detail":"Hold the key as a family: word shares, any two open the home, FamilyOS keeps none. You can do this later.","done":false,"optional":true,"on":false}
    ],"done":1,"total":6,"complete":false,"dismissed":false,"show":true,"wizard":false}
    """)
}

#Preview("Setup checklist") {
    NavigationStack { ScrollView { SetupChecklistCard(sample: PreviewData.setup).padding(Spacing.gutter) }.paper() }
}

#Preview("Setup checklist · dark, large text") {
    NavigationStack { ScrollView { SetupChecklistCard(sample: PreviewData.setup).padding(Spacing.gutter) }.paper() }
        .preferredColorScheme(.dark).dynamicTypeSize(.xxxLarge)
}
