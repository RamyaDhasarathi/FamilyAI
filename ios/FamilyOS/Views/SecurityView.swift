import SwiftUI

/// Security, one page: who holds the household's key, where the household's
/// words are read, and the passkeys that sign this member in. Each is its
/// own screen; this page says what each one is for.
struct SecurityView: View {
    @State private var key: FamilyKeyStatus?
    @State private var models: HouseholdModels?
    @State private var passkeys: [Passkey]?

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: Spacing.s) {
                    Text("Family-held key, where your words are read, passkeys").font(Theme.font(17, .semibold)).foregroundStyle(Theme.ink)
                    Text("Who can open the household’s files, which model reads its notices and answers its questions, and how you sign in without a mailed link.")
                        .font(Theme.font(13)).foregroundStyle(Theme.ink2)
                }
                .padding(.vertical, Spacing.xs)
                .accessibilityElement(children: .combine)
            }
            Section {
                NavigationLink { FamilyKeyView() } label: {
                    row("key", "Family key", key.map { $0.heldByFamily ? ($0.locked ? "Held by the family · locked" : "Held by the family · unlocked") : "Held by the server" })
                }
                NavigationLink { ModelRoutingView() } label: {
                    row("cpu", "Where your words are read", models.map { "Never below \($0.routing.floor)" })
                }
                NavigationLink { PasskeysView() } label: {
                    row("person.badge.key", "Passkeys", passkeys.map { $0.isEmpty ? "None yet" : "\($0.count) on this account" })
                }
            }
            Color.clear.frame(height: 80).listRowBackground(Color.clear).listRowInsets(EdgeInsets())
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Security")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .refreshable { await load() }
    }

    private func row(_ symbol: String, _ title: String, _ detail: String?) -> some View {
        HStack(spacing: Spacing.m) {
            Image(systemName: symbol).foregroundStyle(Theme.ink2).frame(width: 24).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).foregroundStyle(Theme.ink)
                if let detail { Text(detail).font(Theme.font(12)).foregroundStyle(Theme.ink3) }
            }
        }
        .accessibilityElement(children: .combine)
    }

    /// The one-line summaries; a screen that fails here says so on its own page.
    private func load() async {
        async let k = try? API.shared.familyKey()
        async let m = try? API.shared.householdModels()
        async let p = try? API.shared.passkeys()
        (key, models, passkeys) = await (k, m, p)
    }
}

// MARK: where the words are read

/// Which model reads the household's notices and which answers Ask, each
/// with its trust class, and the floor below which words are refused
/// rather than sent. A guardian chooses; everyone sees.
struct ModelRoutingView: View {
    @EnvironmentObject var session: Session
    @State private var models: HouseholdModels?
    @State private var choice: ModelRouting?
    @State private var error: String?
    @State private var refused: String?
    @State private var saved = false
    @State private var busy = false
    var preview: HouseholdModels? = nil

    private var guardian: Bool { session.member?.role == "guardian" }

    var body: some View {
        List {
            if let error { Section { ErrorState(text: error) { Task { await load() } } }.listRowInsets(EdgeInsets()).listRowBackground(Color.clear) }
            if let m = models {
                Section {
                    Text("Notices are read, and questions answered, by a language model.").font(Theme.font(14)).foregroundStyle(Theme.ink2)
                    trustLine("cloud", m.trust.cloud)
                    trustLine("confidential", m.trust.confidential)
                    trustLine("own", m.trust.own)
                }
                Section("Models") {
                    ForEach(m.profiles) { p in
                        HStack(spacing: Spacing.m) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(p.title).font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                                Text([p.model, "runs at " + (p.where ?? "this server")].compactMap { $0 }.joined(separator: " · ") + (p.available == false ? " · not available" : ""))
                                    .font(Theme.font(12)).foregroundStyle(Theme.ink3)
                            }
                            Spacer()
                            Tag(text: p.trust, tint: p.trust == "cloud" ? Theme.warning : Theme.success)
                        }
                        .accessibilityElement(children: .combine)
                    }
                }
                if choice != nil {
                    Section {
                        Picker("Reads notices", selection: binding(\.extraction)) { ForEach(m.profiles) { Text("\($0.title) · \($0.trust)").tag($0.name) } }
                        Picker("Answers Ask", selection: binding(\.ask)) { ForEach(m.profiles) { Text("\($0.title) · \($0.trust)").tag($0.name) } }
                        Picker("Never below", selection: binding(\.floor)) { ForEach(HouseholdModels.classes, id: \.self) { Text($0).tag($0) } }
                        if let refused { Label(refused, systemImage: "hand.raised").font(Theme.font(13)).foregroundStyle(Theme.danger) }
                        if guardian {
                            Button { Task { await save() } } label: { Text(saved ? "Saved" : "Save").font(Theme.font(15, .semibold)) }
                                .foregroundStyle(Theme.primary).disabled(choice == m.routing)
                        } else {
                            Text("A guardian chooses.").font(Theme.font(13)).foregroundStyle(Theme.ink3)
                        }
                    } header: { Text("This household") } footer: {
                        Text("A choice below the floor is refused, never quietly sent somewhere else. Models beyond the default are added by whoever runs this server.")
                    }
                    .disabled(!guardian)
                }
            } else if error == nil {
                Section { LoadingRows(count: 3) }.listRowInsets(EdgeInsets()).listRowBackground(Color.clear)
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Where your words are read")
        .navigationBarTitleDisplayMode(.inline)
        .disabled(busy)
        .sensoryFeedback(.success, trigger: saved)
        .task {
            if let preview { models = preview; choice = preview.routing; return }
            await load()
        }
        .refreshable { await load() }
    }

    private func trustLine(_ name: String, _ meaning: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: Spacing.s) {
            Text(name).font(Theme.font(13, .semibold)).foregroundStyle(name == "cloud" ? Theme.warning : Theme.success).frame(width: 96, alignment: .leading)
            Text(meaning).font(Theme.font(13)).foregroundStyle(Theme.ink2)
        }
        .accessibilityElement(children: .combine)
    }

    private func binding(_ key: WritableKeyPath<ModelRouting, String>) -> Binding<String> {
        Binding(get: { choice?[keyPath: key] ?? "" }, set: { choice?[keyPath: key] = $0; refused = nil; saved = false })
    }

    private func load() async {
        do { let m = try await API.shared.householdModels(); models = m; choice = m.routing; error = nil }
        catch { self.error = error.localizedDescription }
    }

    /// Sends only what changed. The server's refusal (below the floor, not
    /// a guardian) is shown as it is written.
    private func save() async {
        guard let m = models, let c = choice else { return }
        busy = true; defer { busy = false }
        do {
            let out = try await API.shared.setHouseholdModels(extraction: c.extraction == m.routing.extraction ? nil : c.extraction,
                                                              ask: c.ask == m.routing.ask ? nil : c.ask,
                                                              floor: c.floor == m.routing.floor ? nil : c.floor)
            models = out; choice = out.routing; refused = nil; saved = true
        } catch { refused = error.localizedDescription }
    }
}

// MARK: passkeys

/// This member's passkeys: where each was made, when it was last used, and
/// the way to remove one. A passkey is added in the console in Safari: an
/// app making one itself needs Apple's Associated Domains, which needs a
/// paid developer team and the server on a web address of its own.
struct PasskeysView: View {
    @State private var keys: [Passkey]?
    @State private var error: String?
    @State private var removing: Passkey?
    var preview: [Passkey]? = nil

    var body: some View {
        List {
            Section {
                Text("A passkey lets you sign in with Face ID or the device unlock: nothing to type, nothing to phish, no email to wait for. FamilyOS keeps only a public key, bound to the address it was made at.")
                    .font(Theme.font(14)).foregroundStyle(Theme.ink2)
            }
            if let error { Section { ErrorState(text: error) { Task { await load() } } }.listRowInsets(EdgeInsets()).listRowBackground(Color.clear) }
            if let keys {
                Section("Yours") {
                    if keys.isEmpty { Text("None yet.").foregroundStyle(Theme.ink3) }
                    ForEach(keys) { k in
                        HStack(spacing: Spacing.m) {
                            Glyph(symbol: "person.badge.key", tint: Theme.primary, size: 34)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(k.label).foregroundStyle(Theme.ink)
                                Text(detail(k)).font(Theme.font(12)).foregroundStyle(Theme.ink3)
                            }
                        }
                        .accessibilityElement(children: .combine)
                        .swipeActions { Button(role: .destructive) { removing = k } label: { Label("Remove", systemImage: "trash") } }
                        .contextMenu { Button(role: .destructive) { removing = k } label: { Label("Remove", systemImage: "trash") } }
                    }
                }
            } else if error == nil {
                Section { LoadingRows(count: 2) }.listRowInsets(EdgeInsets()).listRowBackground(Color.clear)
            }
            Section {
                Text("Add a passkey in the web console, in Safari on this phone: Household, then Passkeys. It then shows up here. This app cannot make one itself yet; that needs Apple’s paid developer programme and the server on a web address of its own.")
                    .font(Theme.font(13)).foregroundStyle(Theme.ink2)
                if let url = consoleHousehold {
                    Button { UIApplication.shared.open(url) } label: { Label("Open the console in Safari", systemImage: "safari") }
                        .foregroundStyle(Theme.primary)
                }
            } header: { Text("Adding one") } footer: { Text("Remove a passkey when a device is lost; signing in there stops.") }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Passkeys")
        .navigationBarTitleDisplayMode(.inline)
        .confirmationDialog("Remove this passkey?", isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } }), titleVisibility: .visible, presenting: removing) { k in
            Button("Remove \(k.label)", role: .destructive) { Task { await remove(k) } }
            Button("Keep it", role: .cancel) {}
        } message: { _ in Text("That device can no longer sign in with it.") }
        .task {
            if let preview { keys = preview; return }
            await load()
        }
        .refreshable { await load() }
    }

    private var consoleHousehold: URL? {
        guard let base = Server.baseURL else { return nil }
        let root = base.absoluteString.hasSuffix("/") ? String(base.absoluteString.dropLast()) : base.absoluteString
        return URL(string: root + "/app/#/household")
    }

    private func detail(_ k: Passkey) -> String {
        var parts = [k.lastUsedAt.map { "last used " + Format.day.string(from: $0) } ?? "not used yet"]
        if k.backedUp { parts.append("kept by a password manager") }
        if let rp = k.rpId { parts.append("for " + rp) }
        return parts.joined(separator: " · ")
    }

    private func load() async {
        do { keys = try await API.shared.passkeys(); error = nil } catch { self.error = error.localizedDescription }
    }
    private func remove(_ k: Passkey) async {
        do { try await API.shared.removePasskey(k.id); await load() } catch { self.error = error.localizedDescription }
    }
}

// MARK: previews

enum SecuritySample {
    static let models: HouseholdModels = PreviewData.decode("""
    {"profiles":[
      {"name":"default","kind":"deployment default","model":"claude-sonnet","trust":"cloud","where":"the hosted provider","available":true},
      {"name":"mac-mini","kind":"openai-compatible","model":"qwen3-14b","trust":"own","where":"192.168.1.20","available":true}
    ],
    "routing":{"extraction":"default","ask":"default","floor":"cloud"},
    "trust":{"cloud":"a model provider sees the text it is sent","confidential":"processed inside a verified trusted-execution environment run by a third party","own":"a machine the family or its operator controls"}}
    """)
    static let passkeys: [Passkey] = PreviewData.decode("""
    [{"id":"99999999-0000-0000-0000-000000000001","label":"Arun's iPhone","rp_id":"familyos.example.ts.net","backed_up":true,"created_at":"2026-10-12T09:30:00Z","last_used_at":"2026-10-14T07:55:00Z"},
     {"id":"99999999-0000-0000-0000-000000000002","label":"MacBook","rp_id":"familyos.example.ts.net","backed_up":false,"created_at":"2026-10-13T21:10:00Z","last_used_at":null}]
    """)
}

#Preview("Security") { NavigationStack { SecurityView() }.environmentObject(FamilyKeySample.session()) }
#Preview("Where words are read") { NavigationStack { ModelRoutingView(preview: SecuritySample.models) }.environmentObject(FamilyKeySample.session()) }
#Preview("Passkeys, dark") { NavigationStack { PasskeysView(preview: SecuritySample.passkeys) }.environmentObject(FamilyKeySample.session()).preferredColorScheme(.dark) }
