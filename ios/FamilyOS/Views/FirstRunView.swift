import AuthenticationServices
import SwiftUI

/// A text field as the first-run screens draw it.
struct FirstRunField: ViewModifier {
    func body(content: Content) -> some View {
        content.font(Theme.font(16)).padding(14).background(Theme.paper)
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(Theme.line))
    }
}

/// What a new guardian sees once, over the app: the home's name, the family, how to reach it from the phone, and what mail would mean.
/// One question a screen, a reason on each personal one, Skip on everything but the name. The server's checklist (`/household/onboarding`)
/// is the memory: answering the name step ends these screens for good, and what is left stays on the Today card.
struct FirstRunView: View {
    @EnvironmentObject var session: Session
    let start: Session.FirstRunStart

    private enum Step { case name, family, channel, mail, done }

    @State private var step: Step
    @State private var botAvailable = false
    @State private var homeName = ""
    @State private var savedName = ""
    @State private var children = [NewChild()]
    @State private var partnerName = ""
    @State private var partnerEmail = ""
    @State private var familySaved = false
    @State private var familyAdded: [String] = []
    @State private var channelLinked = false
    @State private var mailConnected = false
    @State private var busy = false
    @State private var error: String?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var phase

    init(start: Session.FirstRunStart) {
        self.start = start
        _step = State(initialValue: start == .name ? .name : .family)
    }

    private var steps: [Step] { (start == .name ? [Step.name] : []) + [.family] + (botAvailable ? [.channel] : []) + [.mail, .done] }
    private var index: Int { steps.firstIndex(of: step) ?? 0 }
    private var firstName: String { (session.member?.displayName ?? "").split(separator: " ").first.map(String.init) ?? "" }

    var body: some View {
        VStack(spacing: 0) {
            header
            ScrollView {
                VStack(alignment: .leading, spacing: Spacing.xl) {
                    content
                    if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger) }
                }
                .padding(.horizontal, Spacing.xl).padding(.top, Spacing.l).padding(.bottom, Spacing.xl)
            }
            .scrollDismissesKeyboard(.interactively)
            footer
        }
        .paper()
        .task {
            if let h = try? await API.shared.household() {
                botAvailable = h.telegramBot != nil
                savedName = h.name
                if homeName.isEmpty { homeName = h.name }
            }
        }
        .onChange(of: phase) { _, now in if now == .active, step == .channel { Task { await refreshChannel() } } }
    }

    // MARK: the frame

    private var header: some View {
        VStack(spacing: Spacing.m) {
            HStack {
                if index > 0 && step != .done {
                    Button { go(steps[index - 1]) } label: { Image(systemName: "chevron.left").font(.system(size: 17, weight: .semibold)) }
                        .foregroundStyle(Theme.ink2).accessibilityLabel("Back")
                }
                Spacer()
            }
            .frame(height: 28)
            ProgressView(value: Double(index), total: Double(max(steps.count - 1, 1)))
                .tint(Theme.primary).accessibilityLabel("Step \(index + 1) of \(steps.count)")
        }
        .padding(.horizontal, Spacing.xl).padding(.top, Spacing.m)
    }

    private var footer: some View {
        VStack(spacing: Spacing.m) {
            PrimaryButton(title: primaryTitle) { Task { await primary() } }.disabled(busy || !canContinue)
            if let skip = skipTitle { Button(skip) { Task { await skipStep() } }.font(Theme.font(15, .medium)).foregroundStyle(Theme.ink3).disabled(busy) }
        }
        .padding(.horizontal, Spacing.xl).padding(.bottom, Spacing.xl).padding(.top, Spacing.s)
    }

    private var primaryTitle: String {
        switch step {
        case .name, .family: return busy ? "Saving…" : "Continue"
        case .channel: return channelLinked ? "Continue" : "Open Telegram"
        case .mail: return mailConnected ? "Continue" : "Connect Google"
        case .done: return "Go to Today"
        }
    }

    private var skipTitle: String? {
        switch step {
        case .family: return "Skip for now"
        case .channel: return channelLinked ? nil : "Skip for now"
        case .mail: return mailConnected ? nil : "Skip for now"
        default: return nil
        }
    }

    private var canContinue: Bool {
        step != .name || !homeName.trimmingCharacters(in: .whitespaces).isEmpty
    }

    private func go(_ next: Step) {
        error = nil
        withAnimation(Motion.gentle(reduceMotion)) { step = next }
    }

    private var next: Step { steps[min(index + 1, steps.count - 1)] }

    // MARK: the screens

    @ViewBuilder private var content: some View {
        switch step {
        case .name: nameScreen
        case .family: familyScreen
        case .channel: channelScreen
        case .mail: mailScreen
        case .done: doneScreen
        }
    }

    private func title(_ text: String, _ detail: String) -> some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            Text(text).font(Theme.font(28, .regular, .serif)).foregroundStyle(Theme.ink).accessibilityAddTraits(.isHeader)
            Text(detail).font(Theme.font(16)).foregroundStyle(Theme.ink2)
        }
    }

    private func why(_ text: String) -> some View {
        DisclosureGroup {
            Text(text).font(Theme.font(13)).foregroundStyle(Theme.ink2).frame(maxWidth: .infinity, alignment: .leading).padding(.top, Spacing.xs)
        } label: {
            Label("Why I ask", systemImage: "info.circle").font(Theme.font(14, .medium)).foregroundStyle(Theme.ink2)
        }
        .tint(Theme.ink3).padding(Spacing.m).background(Theme.primaryTint.opacity(0.5)).clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private var nameScreen: some View {
        VStack(alignment: .leading, spacing: Spacing.xl) {
            title(firstName.isEmpty ? "Hello" : "Hello, \(firstName)", "What is your family called? It heads the day's brief and what you share with each other.")
            TextField("The Rao family", text: $homeName).textInputAutocapitalization(.words).modifier(FirstRunField())
                .accessibilityLabel("Your family's name")
        }
    }

    private var familyScreen: some View {
        VStack(alignment: .leading, spacing: Spacing.xl) {
            title("Who is in your family?", "Children first: a name and an age is enough to tell whose school mail is whose.")
            if familySaved {
                VStack(alignment: .leading, spacing: Spacing.s) {
                    ForEach(familyAdded, id: \.self) { Label($0, systemImage: "checkmark.circle.fill").foregroundStyle(Theme.success).font(Theme.font(15)) }
                    if familyAdded.isEmpty { Text("Nobody added yet. You can do it from Family any time.").font(Theme.font(14)).foregroundStyle(Theme.ink3) }
                }
            } else {
                VStack(alignment: .leading, spacing: Spacing.m) {
                    ForEach($children) { $child in
                        HStack(spacing: Spacing.s) {
                            TextField("Child's first name", text: $child.name).textInputAutocapitalization(.words).modifier(FirstRunField())
                            TextField("Age", text: $child.age).keyboardType(.numberPad).modifier(FirstRunField()).frame(width: 84)
                            if children.count > 1 {
                                Button { children.removeAll { $0.id == child.id } } label: { Image(systemName: "xmark").foregroundStyle(Theme.ink3) }
                                    .accessibilityLabel("Remove this child")
                            }
                        }
                    }
                    Button { children.append(NewChild()) } label: { Label("Add another", systemImage: "plus").font(Theme.font(15, .semibold)) }
                        .foregroundStyle(Theme.primary)
                }
                VStack(alignment: .leading, spacing: Spacing.m) {
                    Text("A partner or another adult").font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                    TextField("Their first name", text: $partnerName).textInputAutocapitalization(.words).modifier(FirstRunField())
                    TextField("Their email", text: $partnerEmail).keyboardType(.emailAddress).textInputAutocapitalization(.never).autocorrectionDisabled().modifier(FirstRunField())
                    Text("They get a link to sign in. They do not need to connect any mail of their own.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                }
                why("An age and a first name are used to tell whose school mail is whose, and to know who is a child. Nothing else about a child is asked, and an adult you add sees only what is shared with them.")
            }
        }
    }

    private var channelScreen: some View {
        VStack(alignment: .leading, spacing: Spacing.xl) {
            title("Message it from your phone", "The day's brief and your replies can come to Telegram, so you need not open the app. Opening it links this account once.")
            VStack(alignment: .leading, spacing: Spacing.s) {
                bubble("Morning. School lunch order closes at noon. Nothing else needs you today.", mine: false)
                bubble("ok, doing it now", mine: true)
            }
            .padding(Spacing.l).background(Theme.primaryTint.opacity(0.5)).clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
            .accessibilityElement(children: .ignore).accessibilityLabel("An example: the brief says the lunch order closes at noon, and you reply that you are doing it now.")
            if channelLinked { Label("Linked", systemImage: "checkmark.circle.fill").foregroundStyle(Theme.success).font(Theme.font(15, .semibold)) }
            why("Telegram is where replies and the morning brief reach you. Messages go to the bot only, nothing is posted to any chat, and you can unlink it in Settings.")
        }
    }

    private func bubble(_ text: String, mine: Bool) -> some View {
        Text(text).font(Theme.font(14)).foregroundStyle(mine ? .white : Theme.ink).padding(.horizontal, 12).padding(.vertical, 8)
            .background(mine ? Theme.primary : Theme.paper).clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .frame(maxWidth: .infinity, alignment: mine ? .trailing : .leading)
    }

    private var mailScreen: some View {
        VStack(alignment: .leading, spacing: Spacing.xl) {
            title("Your mail and calendar", "This is what reading them would ask of Google, shown first so nothing is a surprise.")
            VStack(alignment: .leading, spacing: Spacing.m) {
                ask("envelope", "Read your mail", "To find dates, forms and bills in school and bill mail.", asked: true)
                ask("calendar", "Read your calendar", "To see clashes before a date is proposed.", asked: true)
                ask("paperplane", "Send mail for you", "Not asked. Anything sent is a separate choice, made later, one message at a time.", asked: false)
            }
            if mailConnected { Label("Connected. I will start reading now.", systemImage: "checkmark.circle.fill").font(Theme.font(15)).foregroundStyle(Theme.success) }
            why("Mail is where most school circulars and bills arrive. Reading is all that is asked; nothing is deleted or sent, and you can disconnect it whenever you like.")
        }
    }

    private func ask(_ symbol: String, _ title: String, _ detail: String, asked: Bool) -> some View {
        HStack(alignment: .top, spacing: Spacing.m) {
            Image(systemName: symbol).foregroundStyle(asked ? Theme.primary : Theme.ink3).frame(width: 28)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: Spacing.s) {
                    Text(title).font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                    Text(asked ? "ASKED" : "NOT ASKED").font(Theme.font(10, .semibold)).foregroundStyle(Theme.ink3)
                        .padding(.horizontal, 6).padding(.vertical, 2).background(Theme.line).clipShape(Capsule())
                }
                Text(detail).font(Theme.font(13)).foregroundStyle(Theme.ink2)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private var doneScreen: some View {
        VStack(alignment: .leading, spacing: Spacing.xl) {
            title("You're set", "Today shows what needs you. The setup card there keeps what is left: your mail, making it private, and more family.")
            VStack(alignment: .leading, spacing: Spacing.s) {
                Label(homeName.isEmpty ? "Your home is named" : "\(homeName) is set up", systemImage: "checkmark.circle.fill")
                ForEach(familyAdded, id: \.self) { Label($0, systemImage: "checkmark.circle.fill") }
                if channelLinked { Label("Telegram is linked", systemImage: "checkmark.circle.fill") }
            }
            .font(Theme.font(15)).foregroundStyle(Theme.success)
        }
    }

    // MARK: what each button does

    private func primary() async {
        switch step {
        case .name: await saveName()
        case .family: await saveFamily()
        case .channel: if channelLinked { go(next) } else { await openTelegram() }
        case .mail: if mailConnected { go(next) } else { await connectMail() }
        case .done: await finish()
        }
    }

    private func skipStep() async {
        switch step {
        case .channel:
            _ = try? await API.shared.answerOnboarding("skip_channel")
            go(next)
        case .mail:
            _ = try? await API.shared.answerOnboarding("skip_mail")
            go(next)
        default: go(next)
        }
    }

    private func saveName() async {
        busy = true; error = nil; defer { busy = false }
        let name = homeName.trimmingCharacters(in: .whitespaces)
        do {
            if name != savedName { try await API.shared.renameHousehold(name) }
            try await API.shared.answerOnboarding("named")
            go(next)
        } catch { self.error = error.localizedDescription }
    }

    /// Children and the partner are sent together, once. Going back and forward again does not add them twice.
    private func saveFamily() async {
        if familySaved { go(next); return }
        busy = true; error = nil; defer { busy = false }
        do {
            var added: [String] = []
            for child in children where child.isFilled {
                guard let born = child.dateOfBirth() else { continue }
                let n = child.name.trimmingCharacters(in: .whitespaces)
                try await API.shared.addChild(n, born: born)
                added.append(n)
            }
            let p = partnerName.trimmingCharacters(in: .whitespaces), e = partnerEmail.trimmingCharacters(in: .whitespaces)
            if !p.isEmpty, e.contains("@") {
                try await API.shared.addAdultAndInvite(p, email: e)
                added.append("\(p) is invited")
            } else if !p.isEmpty || !e.isEmpty {
                error = "An adult needs a name and an email address, or leave both empty."
                return
            }
            familyAdded = added; familySaved = true
            await session.refreshHousehold()
            go(next)
        } catch { self.error = error.localizedDescription }
    }

    private func openTelegram() async {
        busy = true; error = nil; defer { busy = false }
        do {
            let link = try await API.shared.telegramLink()
            if let url = URL(string: link.url) { await UIApplication.shared.open(url) }
        } catch let e as APIError where e.status == 503 {
            botAvailable = false; go(.mail)
        } catch { self.error = error.localizedDescription }
    }

    /// Back from Telegram: ask the checklist whether the link took.
    private func refreshChannel() async {
        guard let o = try? await API.shared.onboarding() else { return }
        if o.steps.first(where: { $0.key == "channel" })?.done == true { channelLinked = true }
    }

    private func connectMail() async {
        busy = true; error = nil; defer { busy = false }
        do { if try await MailConnect.run() { mailConnected = true } }
        catch let e as APIError where e.status == 503 { error = "Mail is not set up on this server." }
        catch { self.error = error.localizedDescription }
    }

    private func finish() async {
        await session.refreshHousehold()
        session.firstRun = nil
    }
}

/// Connecting mail and calendar from the phone: Google in the app's web session, then the finish token spent as this signed-in member.
enum MailConnect {
    /// True when the mailbox is connected, false when the person backed out; throws what went wrong.
    @MainActor
    static func run() async throws -> Bool {
        let url = try await API.shared.mailboxAuthorizationURL()
        let back: URL
        do { back = try await WebAuth.run(url, scheme: Server.urlScheme) }
        catch let e as ASWebAuthenticationSessionError where e.code == .canceledLogin { return false }
        switch MailboxOutcome.parse(back) {
        case .finish(let token)?: try await API.shared.finishMailbox(token); return true
        case .cancelled?: return false
        default: throw APIError(status: 0, detail: "Google did not finish connecting the mailbox. Try again.")
        }
    }
}

#Preview("First run · family") { FirstRunView(start: .family).environmentObject(Session()) }
#Preview("First run · name, large type") {
    FirstRunView(start: .name).environmentObject(Session()).environment(\.dynamicTypeSize, .accessibility2)
}
