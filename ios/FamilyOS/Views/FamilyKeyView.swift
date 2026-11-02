import SwiftUI
import UniformTypeIdentifiers

/// The family key: the household's key held as word shares, any t of n of
/// which open it. The console's Family key card on the phone. Shares are
/// secrets: they live only in this screen's state, are never logged or
/// stored, and are dropped (with anything this screen put on the pasteboard)
/// when the screen goes away or a step succeeds.
struct FamilyKeyView: View {
    @EnvironmentObject var session: Session
    @State private var status: FamilyKeyStatus?
    @State private var error: String?
    @State private var said: String?
    @State private var busy = false
    @State private var threshold = 2
    @State private var count = 3
    /// The shares just made, shown once; and whether they replace older ones.
    @State private var made: FamilyKeyShares?
    @State private var remade = false
    @State private var confirmText = ""
    @State private var unlockText = ""
    @State private var reshareText = ""
    @State private var disableText = ""
    /// The recovery phrase just made, shown once; the secret of the device made for the switch-on (held in memory only, handed back, then
    /// retired: this phone keeps none); and whether the phrase is a replacement.
    @State private var phrase: String?
    @State private var pendingDevice: PendingDevice?
    @State private var phraseIsNew = false
    @State private var saved = false
    @State private var recoverText = ""
    @State private var disablePhrase = ""
    @State private var copied: Int?
    /// The pasteboard's change count right after this screen copied a share,
    /// so leaving can clear it without reading what is there.
    @State private var pasteboardMark: Int?

    var preview: FamilyKeyStatus? = nil
    var previewShares: FamilyKeyShares? = nil
    var previewPhrase: String? = nil

    private struct PendingDevice { let id: String; let secret: String }

    private var guardian: Bool { session.member?.role == "guardian" }

    var body: some View {
        List {
            if let error { Section { ErrorState(text: error) { Task { await load() } } }.listRowInsets(EdgeInsets()).listRowBackground(Color.clear) }
            if let said {
                Section { Label(said, systemImage: "checkmark.circle").font(Theme.font(14, .semibold)).foregroundStyle(Theme.success) }
            }
            if let s = status {
                if s.heldByFamily { if s.isSimple { simpleHeld(s) } else { familyHeld(s) } } else { serverHeld(s) }
                if let phrase { phraseSections(phrase) }
                if let made { madeSections(made) }
                Section {
                    Text("Protects the original files, the mailbox connection and signed-in sessions, at rest and in backups, and the text read out of notices once it is sealed. It does not hide what FamilyOS reads while the household is unlocked, or from the model provider doing the reading.")
                        .font(Theme.font(13)).foregroundStyle(Theme.ink2)
                } header: { Text("What it does not do") }
            } else if error == nil {
                Section { LoadingRows(count: 2) }.listRowInsets(EdgeInsets()).listRowBackground(Color.clear)
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Family key")
        .navigationBarTitleDisplayMode(.inline)
        .disabled(busy)
        .sensoryFeedback(.success, trigger: copied)
        .task {
            if let preview { status = preview; made = previewShares; phrase = previewPhrase; return }
            await load()
        }
        .refreshable { await load() }
        .onDisappear { forget() }
    }

    // MARK: the server holds the key

    @ViewBuilder
    private func serverHeld(_ s: FamilyKeyStatus) -> some View {
        Section {
            stateLine("Held by the server", symbol: "server.rack", tint: Theme.ink3)
            Text("Make your family’s home private to your family. One tap makes a recovery phrase for you to keep. After that FamilyOS holds no key it can open the home with on its own.")
                .font(Theme.font(14)).foregroundStyle(Theme.ink2)
            if s.pending && made == nil && phrase == nil && guardian {
                Text("A switch-on was started earlier and never finished, so nothing changed. Start again to switch on.").font(Theme.font(13)).foregroundStyle(Theme.warning)
            }
        }
        if guardian {
            if phrase == nil && made == nil {
                Section {
                    Button { Task { await makePrivate() } } label: { Label("Make it private", systemImage: "lock.shield").font(Theme.font(16, .semibold)) }
                        .foregroundStyle(Theme.primary)
                } footer: {
                    Text("You will be shown a recovery phrase once. Save it: it is the only way in if every trusted device is lost.")
                }
                Section {
                    DisclosureGroup("Advanced: split among several people") {
                        Text("Instead of one phrase, make word shares and give them to different people; any few open the household. FamilyOS keeps no share.")
                            .font(Theme.font(13)).foregroundStyle(Theme.ink2)
                        sizePickers
                        Button { Task { await begin() } } label: { Text("Make the shares").font(Theme.font(15, .semibold)) }
                            .foregroundStyle(Theme.primary)
                        Text("Any \(threshold) of \(count) shares will open the household. Give each to a different person, and never keep two together.")
                            .font(Theme.font(12)).foregroundStyle(Theme.ink3)
                    }
                }
            }
        } else {
            Section { Text("A guardian can switch this on.").font(Theme.font(13)).foregroundStyle(Theme.ink3) }
        }
    }

    // MARK: private with one recovery phrase

    @ViewBuilder
    private func simpleHeld(_ s: FamilyKeyStatus) -> some View {
        Section {
            if s.locked {
                stateLine("Locked", symbol: "lock.fill", tint: Theme.warning)
                Text("Everything sealed stays unreadable until someone opens it. On this phone, use the recovery phrase. Unlocking with a passkey needs the phone’s associated domain, which is not set up yet; in a browser you can unlock with a passkey.")
                    .font(Theme.font(14)).foregroundStyle(Theme.ink2)
            } else {
                stateLine("Unlocked", symbol: "lock.open", tint: Theme.success)
                Text("Open for about \(s.unlockedForMinutes) more minutes, then it locks again.").font(Theme.font(14)).foregroundStyle(Theme.ink2)
                Button { Task { await lock() } } label: { Label("Lock now", systemImage: "lock") }.foregroundStyle(Theme.primary)
            }
        } header: { Text("Private to your family") }
        if s.locked {
            Section {
                SharesEntry(text: $recoverText, needed: 1, prompt: "Paste your recovery phrase", action: "Unlock", noun: "phrase") { got in await recover(got[0]) }
            } header: { Text("Use recovery phrase") } footer: { Text("Any adult with the phrase can unlock. It stays open for a few hours, or until someone locks it.") }
        } else if guardian && phrase == nil {
            Section {
                Button { Task { await newPhrase() } } label: { Label("Make a new recovery phrase", systemImage: "arrow.triangle.2.circlepath") }.foregroundStyle(Theme.primary)
                DisclosureGroup("Go back to the server key") {
                    Text("The server holds the household’s key again, as before. The family decides this, not the server, so it needs the recovery phrase.").font(Theme.font(13)).foregroundStyle(Theme.ink2)
                    SharesEntry(text: $disablePhrase, needed: 1, prompt: "Your recovery phrase", action: "Go back", destructive: true, noun: "phrase") { got in await disable(got) }
                }
            } header: { Text("Guardian") } footer: { Text("A new phrase replaces the old one, which then opens nothing. Trusted devices keep working.") }
        }
    }

    // MARK: the recovery phrase, shown once

    @ViewBuilder
    private func phraseSections(_ p: String) -> some View {
        Section {
            Text(phraseIsNew ? "Your new recovery phrase. The old one no longer opens anything." : "Your recovery phrase. FamilyOS does not keep it.")
                .font(Theme.font(14, .semibold)).foregroundStyle(Theme.ink)
            Text(p).font(.system(.footnote, design: .monospaced)).foregroundStyle(Theme.ink).textSelection(.enabled).privacySensitive()
            HStack(spacing: Spacing.l) {
                Button { copy(p, index: 0) } label: { Label(copied == 0 ? "Copied" : "Copy", systemImage: copied == 0 ? "checkmark" : "doc.on.doc") }
                    .buttonStyle(.borderless).foregroundStyle(Theme.primary)
                ShareLink(item: RecoveryPhrase(words: p), preview: SharePreview("FamilyOS recovery phrase", image: Image(systemName: "doc.text"))) {
                    Label("Save or print", systemImage: "square.and.arrow.up")
                }
                .buttonStyle(.borderless).foregroundStyle(Theme.primary)
            }
            .font(Theme.font(14, .medium))
            Toggle("I have saved it somewhere safe", isOn: $saved)
            Button { Task { await donePhrase() } } label: { Text("Done").font(Theme.font(15, .semibold)) }
                .foregroundStyle(saved ? Theme.primary : Theme.ink3).disabled(!saved)
        } header: { Text("Shown once") } footer: {
            Text("A password manager or paper in a drawer. Anyone who has the phrase can open the household, and nobody, including us, can recover it for you. The PDF in the share sheet is a plain page: print it, then delete any copy you saved.")
        }
    }

    // MARK: the family holds the key

    @ViewBuilder
    private func familyHeld(_ s: FamilyKeyStatus) -> some View {
        let t = s.threshold ?? 2
        Section {
            if s.locked {
                stateLine("Locked", symbol: "lock.fill", tint: Theme.warning)
                Text("The files stay sealed until \(t) of the \(s.shares ?? t) shares are given.").font(Theme.font(14)).foregroundStyle(Theme.ink2)
            } else {
                stateLine("Unlocked", symbol: "lock.open", tint: Theme.success)
                Text("Open for about \(s.unlockedForMinutes) more minutes, then it locks again.").font(Theme.font(14)).foregroundStyle(Theme.ink2)
                Button { Task { await lock() } } label: { Label("Lock now", systemImage: "lock") }.foregroundStyle(Theme.primary)
            }
        } header: { Text("Held by the family") }
        if s.locked {
            Section {
                SharesEntry(text: $unlockText, needed: t, prompt: "Paste \(t) shares", action: "Unlock") { got in await unlock(got) }
            } header: { Text("Unlock") } footer: { Text("Any adult can unlock. It stays open for a few hours, or until someone locks it.") }
        }
        if guardian && made == nil {
            Section {
                DisclosureGroup("Make new shares") {
                    sizePickers
                    SharesEntry(text: $reshareText, needed: t, prompt: "The current shares", action: "Make new shares") { got in await reshare(got) }
                }
                DisclosureGroup("Go back to the server key") {
                    Text("The server holds the household’s key again, as before. The family decides this, not the server, so it needs the current shares.").font(Theme.font(13)).foregroundStyle(Theme.ink2)
                    SharesEntry(text: $disableText, needed: t, prompt: "The current shares", action: "Go back", destructive: true) { got in await disable(got) }
                }
            } header: { Text("Guardian") } footer: { Text("Make new shares when someone leaves or a share is lost: the same key, new shares, and the old ones open nothing.") }
        }
    }

    // MARK: the shares, shown once

    @ViewBuilder
    private func madeSections(_ r: FamilyKeyShares) -> some View {
        Section {
            Text(remade ? "New shares. The old ones no longer open anything." : "Write each share on paper, or keep it in a password manager, and give them to \(r.count) different people.")
                .font(Theme.font(14, .semibold)).foregroundStyle(Theme.ink)
            ForEach(Array(r.shares.enumerated()), id: \.offset) { i, share in
                VStack(alignment: .leading, spacing: Spacing.s) {
                    Text("Share \(i + 1) of \(r.count)").font(Theme.font(13, .semibold)).foregroundStyle(Theme.ink3)
                    Text(share).font(.system(.footnote, design: .monospaced)).foregroundStyle(Theme.ink)
                        .textSelection(.enabled).privacySensitive()
                    HStack(spacing: Spacing.l) {
                        Button { copy(share, index: i) } label: { Label(copied == i ? "Copied" : "Copy", systemImage: copied == i ? "checkmark" : "doc.on.doc") }
                            .buttonStyle(.borderless).foregroundStyle(Theme.primary)
                        ShareLink(item: share, subject: Text("FamilyOS recovery share \(i + 1) of \(r.count)")) { Label("Hand to someone", systemImage: "square.and.arrow.up") }
                            .buttonStyle(.borderless).foregroundStyle(Theme.primary)
                    }
                    .font(Theme.font(14, .medium))
                }
                .padding(.vertical, Spacing.xs)
            }
            ShareLink(item: RecoveryKit(shares: r.shares, threshold: r.threshold),
                      preview: SharePreview("FamilyOS recovery kit", image: Image(systemName: "doc.text"))) {
                Label("Print / save the recovery kit", systemImage: "printer")
            }
            .foregroundStyle(Theme.primary)
        } header: { Text("Shown once") } footer: {
            Text("The kit is a PDF: each share’s words numbered, with a line for who holds it. Print it from the share sheet, then delete any copy you saved.")
        }
        if !remade {
            Section {
                SharesEntry(text: $confirmText, needed: r.threshold, prompt: "Paste \(r.threshold) of them back", action: "Switch on the family key") { got in await confirm(got) }
                Button("Put these away, change nothing", role: .cancel) { forget() }.foregroundStyle(Theme.ink3)
            } header: { Text("Switch on") } footer: {
                Text("Nothing has changed yet. Giving \(r.threshold) shares back proves they open the key in use; only then does the server forget its own copy.")
            }
        } else {
            Section { Button("Done, I have handed them out") { forget() }.foregroundStyle(Theme.primary) }
        }
    }

    private var sizePickers: some View {
        Group {
            Picker("Shares needed to open", selection: $threshold) { ForEach([2, 3, 4], id: \.self) { Text("\($0)").tag($0) } }
            Picker("Shares made", selection: $count) { ForEach([3, 4, 5, 6].filter { $0 >= threshold }, id: \.self) { Text("\($0)").tag($0) } }
        }
        .onChange(of: threshold) { _, t in if count < t { count = max(t, 3) } }
    }

    private func stateLine(_ text: String, symbol: String, tint: Color) -> some View {
        HStack(spacing: Spacing.m) {
            Glyph(symbol: symbol, tint: tint, size: 34)
            Text(text).font(Theme.font(17, .semibold)).foregroundStyle(Theme.ink)
        }
        .accessibilityElement(children: .combine)
    }

    // MARK: calls

    private func load() async {
        do { status = try await API.shared.familyKey(); error = nil } catch { self.error = error.localizedDescription }
    }

    private func run(_ work: () async throws -> Void) async {
        busy = true; defer { busy = false }
        said = nil
        do { try await work(); error = nil } catch { self.error = error.localizedDescription }
    }

    private func begin() async {
        await run {
            made = try await API.shared.beginFamilyKey(threshold: threshold, count: count); remade = false
            status = try await API.shared.familyKey()
        }
    }
    private func makePrivate() async {
        await run {
            let r = try await API.shared.makePrivate(label: "iPhone, set up")
            phrase = r.phrase; phraseIsNew = false; saved = false
            pendingDevice = PendingDevice(id: r.device.id, secret: r.device.secret)
        }
    }
    /// Done: if this was the switch-on, hand the device secret back (proving it was kept), then retire that device, since this phone keeps none.
    private func donePhrase() async {
        await run {
            if let d = pendingDevice {
                status = try await API.shared.finishPrivate(deviceId: d.id, deviceSecret: d.secret)
                try? await API.shared.removeFamilyKeyDevice(d.id)
                forget(); said = "It is private now."
            } else {
                forget(); said = "Saved."
            }
        }
    }
    private func newPhrase() async {
        await run {
            let r = try await API.shared.newRecoveryPhrase()
            phrase = r.phrase; phraseIsNew = true; saved = false; pendingDevice = nil
            status = try await API.shared.familyKey()
        }
    }
    private func recover(_ words: String) async {
        await run { status = try await API.shared.recoverFamilyKey(phrase: words); forget(); said = "Unlocked." }
    }
    private func confirm(_ got: [String]) async {
        await run { status = try await API.shared.confirmFamilyKey(shares: got); forget(); said = "The family key is on." }
    }
    private func unlock(_ got: [String]) async {
        await run { status = try await API.shared.unlockFamilyKey(shares: got); forget(); said = "Unlocked." }
    }
    private func lock() async {
        await run { status = try await API.shared.lockFamilyKey(); said = "Locked." }
    }
    private func disable(_ got: [String]) async {
        await run { status = try await API.shared.disableFamilyKey(shares: got); forget(); said = "The server holds the key again." }
    }
    private func reshare(_ got: [String]) async {
        await run {
            let r = try await API.shared.reshareFamilyKey(shares: got, threshold: threshold, count: count)
            forget(); made = r; remade = true
            status = try await API.shared.familyKey()
        }
    }

    // MARK: secrets out

    /// On this phone only (no Universal Clipboard) and gone in two minutes.
    private func copy(_ share: String, index: Int) {
        UIPasteboard.general.setItems([[UTType.utf8PlainText.identifier: share]], options: [.localOnly: true, .expirationDate: Date().addingTimeInterval(120)])
        pasteboardMark = UIPasteboard.general.changeCount
        copied = index
    }

    /// Drops every share this screen holds, and the pasteboard if a share
    /// this screen copied is still what is on it.
    private func forget() {
        phrase = nil; pendingDevice = nil; phraseIsNew = false; saved = false; recoverText = ""; disablePhrase = ""
        made = nil; remade = false
        confirmText = ""; unlockText = ""; reshareText = ""; disableText = ""
        copied = nil
        if let mark = pasteboardMark, UIPasteboard.general.changeCount == mark { UIPasteboard.general.items = [] }
        pasteboardMark = nil
    }
}

/// Where shares are given back: a box to paste or type them into, every 33
/// words one share, a paste button that needs no permission prompt, and how
/// many whole shares were found.
struct SharesEntry: View {
    @Binding var text: String
    let needed: Int
    let prompt: String
    let action: String
    var destructive = false
    var noun = "share"
    let run: ([String]) async -> Void
    @State private var short = false

    var body: some View {
        let got = FamilyKey.parseShares(text)
        VStack(alignment: .leading, spacing: Spacing.s) {
            Text(prompt).font(Theme.font(13, .semibold)).foregroundStyle(Theme.ink3)
            TextEditor(text: $text)
                .font(.system(.footnote, design: .monospaced))
                .autocorrectionDisabled().textInputAutocapitalization(.never)
                .frame(minHeight: 110).scrollContentBackground(.hidden)
                .padding(Spacing.xs).background(Theme.paper).clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                .privacySensitive()
                .accessibilityLabel(prompt)
            HStack {
                PasteButton(payloadType: String.self) { strings in
                    DispatchQueue.main.async { text += (text.isEmpty ? "" : "\n") + strings.joined(separator: "\n") }
                }
                .labelStyle(.titleAndIcon).buttonBorderShape(.capsule).controlSize(.small)
                Spacer()
                Text("\(got.count) of \(needed) \(noun)\(needed == 1 ? "" : "s") · \(FamilyKey.wordCount(text)) words")
                    .font(Theme.font(12)).foregroundStyle(got.count >= needed ? Theme.success : Theme.ink3)
            }
            if short { Text("Paste \(needed) \(noun)\(needed == 1 ? "" : "s"), 33 words each.").font(Theme.font(12)).foregroundStyle(Theme.danger) }
            Button(role: destructive ? .destructive : nil) {
                guard got.count >= needed else { short = true; return }
                short = false
                Task { await run(got) }
            } label: { Text(action).font(Theme.font(15, .semibold)) }
            .buttonStyle(.borderless)
            .foregroundStyle(destructive ? Theme.danger : Theme.primary)
        }
        .padding(.vertical, Spacing.xs)
    }
}

// MARK: the printable kit

/// The recovery kit as a PDF, made only when the share sheet asks for it:
/// a heading, then each share in a dashed box with its 33 words numbered
/// down three columns and a line for who holds it. The console's printed kit.
struct RecoveryKit: Transferable {
    let shares: [String]
    let threshold: Int
    /// One recovery phrase rather than shares among several people: no "held by" line, and its own words.
    var single = false

    static var transferRepresentation: some TransferRepresentation {
        DataRepresentation(exportedContentType: .pdf) { kit in kit.pdf() }
            .suggestedFileName("FamilyOS recovery kit.pdf")
    }

    func pdf() -> Data {
        let page = CGRect(x: 0, y: 0, width: 595, height: 842)   // A4 in points
        let margin: CGFloat = 40, width = page.width - margin * 2
        let ink = UIColor(white: 0.07, alpha: 1), grey = UIColor(white: 0.27, alpha: 1)
        let h1: [NSAttributedString.Key: Any] = [.font: UIFont.systemFont(ofSize: 20, weight: .semibold), .foregroundColor: ink]
        let body: [NSAttributedString.Key: Any] = [.font: UIFont.systemFont(ofSize: 11), .foregroundColor: grey]
        let h2: [NSAttributedString.Key: Any] = [.font: UIFont.systemFont(ofSize: 14, weight: .semibold), .foregroundColor: ink]
        let word: [NSAttributedString.Key: Any] = [.font: UIFont.monospacedSystemFont(ofSize: 11, weight: .regular), .foregroundColor: ink]
        let num: [NSAttributedString.Key: Any] = [.font: UIFont.monospacedDigitSystemFont(ofSize: 9, weight: .regular), .foregroundColor: grey]
        let rows = 11, rowHeight: CGFloat = 17, boxHeight: CGFloat = 60 + CGFloat(rows) * rowHeight

        return UIGraphicsPDFRenderer(bounds: page).pdfData { ctx in
            ctx.beginPage()
            var y = margin
            NSString(string: single ? "FamilyOS recovery phrase" : "FamilyOS recovery kit").draw(at: CGPoint(x: margin, y: y), withAttributes: h1)
            y += 30
            let lead = single
                ? "This phrase opens your family’s home if every trusted device is lost. FamilyOS keeps no copy and cannot recover it. Keep it somewhere safe and private; anyone who has it can open the household."
                : "Any \(threshold) of these \(shares.count) shares open your family’s home. FamilyOS keeps none. Cut along the lines, give each share to a different person or place, and never keep two together. If fewer than \(threshold) survive, nobody can recover the home, including us."
            let leadRect = CGRect(x: margin, y: y, width: width, height: 70)
            NSString(string: lead).draw(with: leadRect, options: [.usesLineFragmentOrigin], attributes: body, context: nil)
            y += NSString(string: lead).boundingRect(with: leadRect.size, options: [.usesLineFragmentOrigin], attributes: body, context: nil).height + 18

            for (i, share) in shares.enumerated() {
                if y + boxHeight > page.height - margin { ctx.beginPage(); y = margin }
                let box = CGRect(x: margin, y: y, width: width, height: boxHeight)
                let path = UIBezierPath(roundedRect: box, cornerRadius: 10)
                path.lineWidth = 1.5; path.setLineDash([6, 4], count: 2, phase: 0)
                UIColor(white: 0.55, alpha: 1).setStroke(); path.stroke()
                NSString(string: single ? "Recovery phrase" : "Recovery share \(i + 1) of \(shares.count)").draw(at: CGPoint(x: margin + 16, y: y + 12), withAttributes: h2)
                if !single { NSString(string: "Held by: ______________________________").draw(at: CGPoint(x: margin + 16, y: y + 32), withAttributes: body) }
                let words = share.split(separator: " ").map(String.init)
                let colWidth = (width - 32) / 3
                for (n, w) in words.enumerated() {
                    let col = n / rows, row = n % rows
                    let x = margin + 16 + CGFloat(col) * colWidth, wy = y + 54 + CGFloat(row) * rowHeight
                    NSString(string: String(format: "%2d.", n + 1)).draw(at: CGPoint(x: x, y: wy + 1.5), withAttributes: num)
                    NSString(string: w).draw(at: CGPoint(x: x + 24, y: wy), withAttributes: word)
                }
                y += boxHeight + 16
            }
        }
    }
}

/// The recovery phrase as a plain one-page PDF, made only when the share sheet asks for it.
struct RecoveryPhrase: Transferable {
    let words: String

    static var transferRepresentation: some TransferRepresentation {
        DataRepresentation(exportedContentType: .pdf) { r in RecoveryKit(shares: [r.words], threshold: 1, single: true).pdf() }
            .suggestedFileName("FamilyOS recovery phrase.pdf")
    }
}

#Preview("Server key, guardian") {
    NavigationStack { FamilyKeyView(preview: FamilyKeySample.server) }.environmentObject(FamilyKeySample.session())
}
#Preview("Shares shown once") {
    NavigationStack { FamilyKeyView(preview: FamilyKeySample.server, previewShares: FamilyKeySample.shares) }.environmentObject(FamilyKeySample.session())
}
#Preview("Recovery phrase shown once") {
    NavigationStack { FamilyKeyView(preview: FamilyKeySample.server, previewPhrase: FamilyKeySample.words) }.environmentObject(FamilyKeySample.session())
}
#Preview("Private, locked") {
    NavigationStack { FamilyKeyView(preview: FamilyKeySample.simpleLocked) }.environmentObject(FamilyKeySample.session())
}
#Preview("Family key, locked, dark") {
    NavigationStack { FamilyKeyView(preview: FamilyKeySample.locked) }.environmentObject(FamilyKeySample.session()).preferredColorScheme(.dark)
}

/// Sample states for previews only; the words are made up, not a real share.
enum FamilyKeySample {
    static let server: FamilyKeyStatus = PreviewData.decode(#"{"mode":"server","threshold":null,"shares":null,"pending":false,"locked":false,"unlocked_for_minutes":0}"#)
    static let locked: FamilyKeyStatus = PreviewData.decode(#"{"mode":"family","threshold":2,"shares":3,"pending":false,"locked":true,"unlocked_for_minutes":0}"#)
    static let simpleLocked: FamilyKeyStatus = PreviewData.decode(#"{"mode":"family","threshold":1,"shares":1,"pending":false,"simple":true,"locked":true,"unlocked_for_minutes":0}"#)
    static let unlocked: FamilyKeyStatus = PreviewData.decode(#"{"mode":"family","threshold":2,"shares":3,"pending":false,"locked":false,"unlocked_for_minutes":412}"#)
    static let words = "academic acid acne acquire acrobat activity actress adapt adequate adjust admit adorn adult advance advocate afraid again agency agree aide aircraft airline airport ajar alarm album alcohol alien alive alpha already alto aluminum"
    static let shares: FamilyKeyShares = PreviewData.decode(#"{"shares":["\#(words)","\#(words)","\#(words)"],"threshold":2,"count":3,"note":"Shown once."}"#)
    @MainActor static func session() -> Session {
        let s = PreviewData.session()
        s.member = PreviewData.members.first
        return s
    }
}
