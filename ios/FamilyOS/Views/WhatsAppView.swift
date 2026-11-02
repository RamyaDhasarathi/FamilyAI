import SwiftUI

/// WhatsApp reading: the chats I name, read every half hour from my own
/// linked WhatsApp Web, so the dates and tasks in them come up as proposals.
/// It reads only the named chats and never sends, replies or reacts. The
/// costs are shown before the yes, and the code to type into WhatsApp is
/// shown large while the server waits for it. Nothing is kept on the phone.
struct WhatsAppView: View {
    @EnvironmentObject var session: Session
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var status: WhatsAppStatus?
    @State private var loaded = false
    @State private var error: String?
    @State private var phone = ""
    @State private var chatsText = ""
    @State private var savingPhone = false
    @State private var savingChats = false
    @State private var tagging: String?
    @State private var linking = false
    @State private var code: String?
    @State private var qr: String?          // while linking by QR: the code is "" and this is the picture
    @State private var codeSeconds = 180
    @State private var linkRun = UUID()
    @State private var understood = false
    @State private var cloudOk = false
    @State private var enabling = false
    @State private var reading = false
    @State private var pass: String?
    @State private var confirmForget = false
    @State private var forgotten: String?
    private let preview: Bool

    init(preview: WhatsAppStatus? = nil) {
        _status = State(initialValue: preview)
        _loaded = State(initialValue: preview != nil)
        _chatsText = State(initialValue: preview?.chats.joined(separator: "\n") ?? "")
        self.preview = preview != nil
    }

    private var guardian: Bool { session.member?.role == "guardian" }
    private var chats: [String] { WhatsAppChats.parse(chatsText) }
    private var chatsChanged: Bool { chats != (status?.chats ?? []) }
    private var tooMany: Bool { chats.count > WhatsAppStatus.maxChats }

    var body: some View {
        ScrollViewReader { proxy in
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 12) {
                    Glyph(symbol: "bubble.left.and.text.bubble.right", tint: Theme.green, size: 44)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("WhatsApp reading").font(Theme.font(24, .medium, .serif)).foregroundStyle(Theme.ink)
                        Text("Only the chats you name").font(Theme.font(13)).foregroundStyle(Theme.ink3)
                    }
                }
                .accessibilityElement(children: .combine).accessibilityAddTraits(.isHeader)
                if session.member?.isChild == true {
                    EmptyState(symbol: "person.badge.shield.checkmark", title: "For grown-ups", text: "Linking WhatsApp is for the adults in the household.")
                } else if let error, status == nil {
                    ErrorState(text: error, retry: { Task { await load() } })
                } else if !loaded {
                    LoadingRows(count: 3)
                } else if let s = status, s.available {
                    content(s)
                } else {
                    EmptyState(symbol: "bubble.left.and.exclamationmark.bubble.right", title: "Not switched on",
                               text: "Whoever runs this FamilyOS server has not turned on WhatsApp reading.")
                }
                BarSpace()
            }
            .padding(16)
        }
        .paper()
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        // The code appears below the costs and the chats: bring it into view, so it is not found by scrolling.
        .onChange(of: code) { _, new in
            guard new != nil else { return }
            if reduceMotion { proxy.scrollTo("link", anchor: .top) } else { withAnimation { proxy.scrollTo("link", anchor: .top) } }
        }
        .onChange(of: loaded) { _, now in
            // A debug launch (`-wa state`) can open on the switch-on or reading card.
            if now, Debug.string("wa") == "state" { proxy.scrollTo("state", anchor: .top) }
            if now, Debug.string("wa") == "whose" { proxy.scrollTo("whose", anchor: .top) }
        }
        .task {
            if preview { return }
            await load()
            // A debug launch can start the link by itself (`-wa link`), so the code screen can be looked at without tapping.
            if Debug.string("wa") == "link", status?.available == true, status?.phoneOnFile == true { await link() }
        }
        // While the code is on screen, ask every 4 s whether it has been typed; it ends when linked, when the code expires, or when the screen goes.
        .task(id: linkRun) {
            guard code != nil, !preview else { return }
            var waited = 0
            while waited < codeSeconds {
                try? await Task.sleep(for: .seconds(4))
                if Task.isCancelled { return }
                waited += 4
                if let fresh = try? await API.shared.whatsAppLinkStatus() {
                    if fresh.linked { status = fresh; code = nil; qr = nil; error = nil; return }
                    if let q = fresh.qr { qr = q }          // the QR rotates every half minute
                }
            }
            code = nil; qr = nil
            error = "The code ran out. Press Link WhatsApp for a new one."
        }
        }
    }

    @ViewBuilder private func content(_ s: WhatsAppStatus) -> some View {
        Text("FamilyOS reads only the chats you name, from your own WhatsApp Web, and turns dates and tasks in them into proposals you accept or not. It never sends, replies or reacts.")
            .font(Theme.font(13)).foregroundStyle(Theme.ink2)
        if let error { Card { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger) } }
        if let forgotten { Card { Text(forgotten).font(Theme.font(14)).foregroundStyle(Theme.ink) } }
        if !s.enabled || s.consentPaused { costs(s) }
        if !s.phoneOnFile { phoneCard }
        chatsCard(s)
        if guardian && s.canTagChats { whoseCard(s).id("whose") }
        linkCard(s).id("link")
        Group {
            VStack(alignment: .leading, spacing: Spacing.l) {
                if s.enabled { readingCard(s) }
                if !s.enabled || s.consentPaused { enableCard(s) }
            }
        }.id("state")
    }

    // MARK: the costs, before the yes

    private func costs(_ s: WhatsAppStatus) -> some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            Heading(title: "What this costs")
            Card {
                VStack(alignment: .leading, spacing: Spacing.m) {
                    ForEach(Array(s.consent.enumerated()), id: \.offset) { _, line in
                        HStack(alignment: .top, spacing: Spacing.s) {
                            Image(systemName: "exclamationmark.circle").font(Theme.font(13, .semibold)).foregroundStyle(Theme.warning).accessibilityHidden(true).padding(.top, 2)
                            Text(line).font(Theme.font(13)).foregroundStyle(Theme.ink2).fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    if let m = s.model {
                        Text("Read by: \(m.where) (\(m.trust)).").font(Theme.font(12, .semibold)).foregroundStyle(Theme.ink3)
                    }
                }
            }
        }
    }

    // MARK: my number

    private var phoneCard: some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            Heading(title: "Your number")
            Card {
                VStack(alignment: .leading, spacing: Spacing.m) {
                    Text("The number your WhatsApp uses, with its country code. WhatsApp links to it.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                    TextField("+91 98765 43210", text: $phone)
                        .keyboardType(.phonePad).textContentType(.telephoneNumber)
                        .font(Theme.font(15)).foregroundStyle(Theme.ink)
                        .padding(10).background(Theme.paper).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .accessibilityLabel("Your phone number with country code")
                    HStack {
                        Spacer()
                        if savingPhone { ProgressView().controlSize(.small) }
                        Button("Save number") { Task { await savePhone() } }
                            .buttonStyle(.borderedProminent).tint(Theme.primary).controlSize(.small)
                            .disabled(savingPhone || phone.filter(\.isNumber).count < 8)
                    }
                }
            }
        }
    }

    // MARK: the chats

    private func chatsCard(_ s: WhatsAppStatus) -> some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            Heading(title: "Chats to read")
            Card {
                VStack(alignment: .leading, spacing: Spacing.m) {
                    Text("One chat per line, exactly as WhatsApp names it. Up to \(WhatsAppStatus.maxChats). Nothing else is ever opened.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                    TextField("Class 2 Parents", text: $chatsText, axis: .vertical)
                        .lineLimit(3...8).font(Theme.font(15)).foregroundStyle(Theme.ink)
                        .textInputAutocapitalization(.words).autocorrectionDisabled()
                        .padding(10).background(Theme.paper).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .accessibilityLabel("Chats to read, one per line")
                    HStack {
                        Text("\(chats.count) of \(WhatsAppStatus.maxChats)").font(Theme.font(12)).foregroundStyle(tooMany ? Theme.danger : Theme.ink3)
                        Spacer()
                        if savingChats { ProgressView().controlSize(.small) }
                        Button("Save chats") { Task { await saveChats() } }
                            .buttonStyle(.borderedProminent).tint(Theme.primary).controlSize(.small)
                            .disabled(savingChats || tooMany || !chatsChanged)
                    }
                }
            }
        }
    }

    // MARK: whose is each chat

    /// One row per saved chat: which school it belongs to, so its messages are attributed to the children there. Guardians only.
    private func whoseCard(_ s: WhatsAppStatus) -> some View {
        let schools = s.schools ?? []
        return VStack(alignment: .leading, spacing: Spacing.s) {
            Heading(title: "Whose is each chat?")
            Card {
                VStack(alignment: .leading, spacing: Spacing.m) {
                    Text("Messages from a chat are attributed to the children at the school you pick.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                    ForEach(s.chats, id: \.self) { chat in
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: Spacing.s) {
                                Text(chat).font(Theme.font(14, .medium)).foregroundStyle(Theme.ink).frame(maxWidth: .infinity, alignment: .leading)
                                if tagging == chat { ProgressView().controlSize(.small) }
                            }
                            Picker(chat, selection: tagBinding(chat, s)) {
                                Text("Nobody in particular").tag("")
                                ForEach(schools) { school in Text(school.label).tag(school.school) }
                            }
                            .pickerStyle(.menu).tint(Theme.primary).labelsHidden()
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .disabled(tagging != nil)
                            .accessibilityLabel("Whose is the chat \(chat)")
                            .accessibilityValue(s.school(of: chat) ?? "Nobody in particular")
                        }
                        .frame(minHeight: 44)
                    }
                }
            }
        }
    }

    private func tagBinding(_ chat: String, _ s: WhatsAppStatus) -> Binding<String> {
        Binding(get: { s.school(of: chat) ?? "" }, set: { new in Task { await tag(chat, school: new) } })
    }

    // MARK: linking

    private func linkCard(_ s: WhatsAppStatus) -> some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            Heading(title: "Link WhatsApp")
            Card {
                VStack(alignment: .leading, spacing: Spacing.m) {
                    HStack(spacing: Spacing.s) {
                        Image(systemName: s.linked ? "checkmark.circle.fill" : (s.lapsed ? "exclamationmark.triangle.fill" : "circle.dashed"))
                            .foregroundStyle(s.linked ? Theme.success : (s.lapsed ? Theme.warning : Theme.ink3)).accessibilityHidden(true)
                        Text(s.linkWords).font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                    }
                    .accessibilityElement(children: .combine)
                    if linking {
                        HStack(spacing: Spacing.s) {
                            ProgressView().controlSize(.small)
                            Text("Opening WhatsApp Web on the server. This can take half a minute.").font(Theme.font(13)).foregroundStyle(Theme.ink3)
                        }
                    }
                    if let shown = code, shown.isEmpty {
                        qrBlock
                    } else if let shown = code {
                        Text("On this phone, open WhatsApp → Settings → Linked devices → Link a device → Link with phone number instead, then type this code:")
                            .font(Theme.font(13)).foregroundStyle(Theme.ink2).fixedSize(horizontal: false, vertical: true)
                        Text(shown)
                            .font(.system(.largeTitle, design: .monospaced).weight(.semibold)).tracking(2)
                            .minimumScaleFactor(0.6).lineLimit(1).foregroundStyle(Theme.ink)
                            .frame(maxWidth: .infinity).padding(.vertical, Spacing.m)
                            .background(Theme.primaryTint).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                            .textSelection(.enabled)
                            .accessibilityLabel("Link code: " + spoken(shown))
                        HStack(spacing: Spacing.s) {
                            ProgressView().controlSize(.small)
                            Text("Waiting for you to type it…").font(Theme.font(13)).foregroundStyle(Theme.ink3)
                            Spacer()
                            Button("Cancel") { code = nil; qr = nil; linkRun = UUID() }.font(Theme.font(13, .semibold)).foregroundStyle(Theme.ink3)
                        }
                    } else if !linking {
                        GhostButton(title: s.linked ? "Link again" : "Link WhatsApp") { Task { await link() } }
                            .disabled(!s.phoneOnFile)
                        if !s.phoneOnFile { Text("Save your number first.").font(Theme.font(12)).foregroundStyle(Theme.ink3) }
                    }
                }
            }
        }
    }

    /// WhatsApp gave no code, so the server's page offers a QR code. This phone cannot scan its own screen: it has to be shown on another one.
    private var qrBlock: some View {
        VStack(alignment: .leading, spacing: Spacing.m) {
            Text("WhatsApp gave no code this time, so it offers a QR code. This phone cannot scan its own screen: show it on another one (FamilyOS on a Mac or iPad, or the web console), then on this phone open WhatsApp → Settings → Linked devices → Link a device and point the camera at it. Or cancel and press Link WhatsApp again to try for a code.")
                .font(Theme.font(13)).foregroundStyle(Theme.ink2).fixedSize(horizontal: false, vertical: true)
            if let data = qr.flatMap({ Data(base64Encoded: $0) }), let image = UIImage(data: data) {
                Image(uiImage: image).interpolation(.none).resizable().scaledToFit()
                    .frame(maxWidth: 240).padding(Spacing.s).background(Color.white).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .frame(maxWidth: .infinity).accessibilityLabel("WhatsApp QR code")
            }
            HStack(spacing: Spacing.s) {
                ProgressView().controlSize(.small)
                Text("Waiting for it to be scanned…").font(Theme.font(13)).foregroundStyle(Theme.ink3)
                Spacer()
                Button("Cancel") { code = nil; qr = nil; linkRun = UUID() }.font(Theme.font(13, .semibold)).foregroundStyle(Theme.ink3)
            }
        }
    }

    /// The code a character at a time, for VoiceOver.
    private func spoken(_ code: String) -> String { code.filter { $0 != "-" }.map { String($0) }.joined(separator: " ") }

    // MARK: switching on

    private func enableCard(_ s: WhatsAppStatus) -> some View {
        let hosted = s.model?.isHosted == true
        let ready = s.linked && !s.chats.isEmpty && understood && (!hosted || cloudOk)
        return VStack(alignment: .leading, spacing: Spacing.s) {
            Heading(title: s.enabled ? "Resume reading" : "Start reading")
            Card {
                VStack(alignment: .leading, spacing: Spacing.m) {
                    Toggle("I have read what this costs", isOn: $understood).font(Theme.font(14)).foregroundStyle(Theme.ink).tint(Theme.primary)
                    if hosted, let m = s.model {
                        Toggle("These chats may be read by \(m.where)", isOn: $cloudOk).font(Theme.font(14)).foregroundStyle(Theme.ink).tint(Theme.primary)
                    }
                    if enabling { ProgressView().controlSize(.small) }
                    PrimaryButton(title: s.enabled ? "Resume reading" : "Start reading every \(s.minutes) minutes") { Task { await enable() } }
                        .disabled(!ready || enabling).opacity(ready ? 1 : 0.5)
                    if !ready {
                        Text(!s.linked ? "Link WhatsApp first." : (s.chats.isEmpty ? "Save at least one chat first." : "Tick the boxes above to switch it on."))
                            .font(Theme.font(12)).foregroundStyle(Theme.ink3)
                    }
                }
            }
        }
    }

    private func readingCard(_ s: WhatsAppStatus) -> some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            Heading(title: "Reading every \(s.minutes) minutes")
            Card {
                VStack(alignment: .leading, spacing: Spacing.m) {
                    detail("Last read", s.lastOkAt.map { $0.formatted(date: .abbreviated, time: .shortened) } ?? "not yet")
                    if let n = s.lastFound, n > 0 { detail("New in the last pass", "\(n)") }
                    if let e = s.lastError, !e.isEmpty { Text(e).font(Theme.font(13)).foregroundStyle(Theme.danger).fixedSize(horizontal: false, vertical: true) }
                    if let pass { Text(pass).font(Theme.font(13)).foregroundStyle(Theme.ink2).fixedSize(horizontal: false, vertical: true) }
                    if reading { ProgressView().controlSize(.small) }
                    GhostButton(title: "Read now") { Task { await readNow() } }.disabled(reading)
                    Button("Stop and forget", role: .destructive) { confirmForget = true }
                        .font(Theme.font(14, .semibold)).foregroundStyle(Theme.danger).frame(minHeight: 44)
                }
            }
        }
        .confirmationDialog("Stop reading WhatsApp?", isPresented: $confirmForget, titleVisibility: .visible) {
            Button("Stop and forget the link", role: .destructive) { Task { await forget() } }
        } message: {
            Text("This deletes the logged-in browser on the server and the chat list. Notices already read stay.")
        }
    }

    private func detail(_ label: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label).font(Theme.font(14)).foregroundStyle(Theme.ink3)
            Spacer()
            Text(value).font(Theme.font(14, .medium)).foregroundStyle(Theme.ink)
        }
        .accessibilityElement(children: .combine)
    }

    // MARK: calls

    private func load() async {
        do {
            let fresh = try await API.shared.whatsApp()
            status = fresh
            if !chatsChanged || chatsText.isEmpty { chatsText = fresh.chats.joined(separator: "\n") }
            error = nil
        } catch { self.error = error.localizedDescription }
        loaded = true
    }

    private func savePhone() async {
        savingPhone = true; defer { savingPhone = false }
        do { try await API.shared.setMyPhone(phone.trimmingCharacters(in: .whitespaces)); phone = ""; error = nil; await load() }
        catch { self.error = error.localizedDescription }
    }

    private func saveChats() async {
        savingChats = true; defer { savingChats = false }
        do { status = try await API.shared.setWhatsAppChats(chats); chatsText = (status?.chats ?? []).joined(separator: "\n"); error = nil }
        catch { self.error = error.localizedDescription }
    }

    /// Tie one saved chat to a school ("" for nobody in particular). The server's sentence is shown if it refuses.
    private func tag(_ chat: String, school: String) async {
        guard let saved = status?.chats, tagging == nil else { return }
        tagging = chat; defer { tagging = nil }
        do { status = try await API.shared.tagWhatsAppChat(chat, school: school, chats: saved); error = nil }
        catch { self.error = error.localizedDescription }
    }

    private func link() async {
        linking = true; defer { linking = false }
        error = nil; forgotten = nil
        do {
            let out = try await API.shared.startWhatsAppLink()
            if out.linked { await load(); return }
            guard out.code != nil || out.qr != nil else { error = "WhatsApp Web gave neither a code nor a QR code."; return }
            codeSeconds = out.expiresIn ?? 180
            qr = out.qr
            code = out.code ?? ""           // "" means: linking by QR
            linkRun = UUID()
        } catch { self.error = error.localizedDescription }
    }

    private func enable() async {
        enabling = true; defer { enabling = false }
        do { status = try await API.shared.enableWhatsApp(understood: understood, cloudOk: cloudOk); understood = false; cloudOk = false; error = nil; forgotten = nil }
        catch { self.error = error.localizedDescription }
    }

    private func readNow() async {
        reading = true; defer { reading = false }
        do {
            let out = try await API.shared.readWhatsAppNow()
            var fresh = out.status
            fresh.tags = status?.tags                // a pass does not change whose a chat is; keep the names as the server held them
            status = fresh; pass = out.result?.words; error = nil
        } catch { self.error = error.localizedDescription }
    }

    private func forget() async {
        do {
            let out = try await API.shared.forgetWhatsApp()
            forgotten = out.note ?? "Forgotten. Also remove FamilyOS in WhatsApp → Settings → Linked devices."
            pass = nil; code = nil; chatsText = ""; error = nil
            await load()
        } catch { self.error = error.localizedDescription }
    }
}

#if DEBUG
#Preview("Linked, not yet reading") {
    NavigationStack {
        WhatsAppView(preview: WhatsAppStatus(available: true, hasPhone: true, needsConsent: false, consent: ["A cost.", "Another cost."], enabled: false, status: "linked",
                                             chats: ["Class 2 Parents"], lastRunAt: nil, lastOkAt: nil, lastError: nil, lastFound: 0, everyMinutes: 30,
                                             model: WhatsAppModel(name: "default", trust: "cloud", where: "the hosted provider"), qr: nil,
                                             schools: [WhatsAppSchool(school: "Bright Start", children: ["Lily"])], tags: ["Class 2 Parents": "Bright Start"], note: nil))
    }
    .environmentObject(PreviewData.session())
}
#endif
