import SwiftUI

/// What FamilyOS was taught: tasks shown to it once on a phone app or a
/// public page, kept as steps by the words on the screen. A web skill can
/// be run from here; a phone skill runs through the phone driver, which
/// runs from the Mac. Teaching a new one happens in the console.
struct SkillsView: View {
    @State private var skills: [TaughtSkill]?
    @State private var error: String?
    @State private var running: UUID?
    /// What the last run said, by skill.
    @State private var outcome: [UUID: (ok: Bool, text: String)] = [:]
    @State private var forgetting: TaughtSkill?
    private let preview: Bool

    init(preview: [TaughtSkill]? = nil) {
        _skills = State(initialValue: preview)
        self.preview = preview != nil
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 12) {
                    Glyph(symbol: "hand.tap", tint: Theme.primary, size: 44)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("What FamilyOS was taught").font(Theme.font(24, .medium, .serif)).foregroundStyle(Theme.ink)
                        Text("Shown once, kept by the words on the screen").font(Theme.font(13)).foregroundStyle(Theme.ink3)
                    }
                }
                .accessibilityElement(children: .combine).accessibilityAddTraits(.isHeader)
                Card {
                    VStack(alignment: .leading, spacing: Spacing.s) {
                        Label("A skill only opens, taps, swipes and reads. It never types, pays, sends or submits, and what it reads comes in as a private notice.", systemImage: "hand.raised")
                            .font(Theme.font(13)).foregroundStyle(Theme.ink2)
                        Label("Teaching a new one happens in the console, on My day. A phone skill runs through the phone driver, which runs from the Mac.", systemImage: "desktopcomputer")
                            .font(Theme.font(13)).foregroundStyle(Theme.ink3)
                    }
                }
                if let error { ErrorState(text: error, retry: { Task { await load() } }) }
                if let skills {
                    if skills.isEmpty {
                        EmptyState(symbol: "hand.tap", title: "Nothing taught yet", text: "Show FamilyOS a task once in the console and it appears here.")
                    } else {
                        VStack(spacing: Spacing.s) { ForEach(skills) { card($0) } }
                    }
                } else if error == nil {
                    LoadingRows(count: 3)
                }
                BarSpace()
            }
            .padding(16)
        }
        .paper()
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task { if !preview { await load() } }
        .confirmationDialog("Forget \(forgetting?.title ?? "this skill")?", isPresented: Binding(get: { forgetting != nil }, set: { if !$0 { forgetting = nil } }), titleVisibility: .visible) {
            Button("Forget it", role: .destructive) { if let k = forgetting { Task { await forget(k) } } }
        }
    }

    private func card(_ k: TaughtSkill) -> some View {
        Card {
            VStack(alignment: .leading, spacing: Spacing.s) {
                HStack(spacing: Spacing.m) {
                    Glyph(symbol: k.isWeb ? "globe" : "iphone", tint: Theme.primary, size: 34)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(k.title).font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                        Text((k.isWeb ? "web page " : "phone app ") + k.target).font(Theme.font(12)).foregroundStyle(Theme.ink3).lineLimit(1).truncationMode(.middle)
                    }
                }
                .accessibilityElement(children: .combine)
                Text(summary(k)).font(Theme.font(12)).foregroundStyle(Theme.ink3)
                if !k.steps.isEmpty {
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(Array(k.steps.enumerated()), id: \.offset) { i, s in
                            Text("\(i + 1). " + describe(s)).font(Theme.font(12)).foregroundStyle(Theme.ink2)
                        }
                    }
                }
                if let o = outcome[k.id] { Text(o.text).font(Theme.font(13)).foregroundStyle(o.ok ? Theme.success : Theme.warning) }
                HStack(spacing: Spacing.s) {
                    if k.isWeb {
                        Button(running == k.id ? "Running…" : "Run now") { Task { await run(k) } }
                            .buttonStyle(.borderedProminent).tint(Theme.primary).controlSize(.small).disabled(running != nil)
                    }
                    Button("Forget") { forgetting = k }.buttonStyle(.bordered).controlSize(.small).disabled(running == k.id)
                    Spacer()
                    if running == k.id { ProgressView().controlSize(.small) }
                }
                .padding(.top, 2)
            }
        }
    }

    private func summary(_ k: TaughtSkill) -> String {
        var s = "\(k.steps.count) step\(k.steps.count == 1 ? "" : "s") · run \(k.runs) time\(k.runs == 1 ? "" : "s")"
        if let at = k.lastRunAt { s += " · last " + Format.stamp.string(from: at) }
        if let o = k.lastOutcome { s += ": " + (o == "done" ? "done" : o.replacingOccurrences(of: "_", with: " ")) }
        return s
    }

    private func describe(_ s: TaughtSkill.Step) -> String {
        switch s.op {
        case "tap": return "Tap “\(s.text ?? "")”"
        case "swipe": return "Swipe \(s.direction ?? "up")"
        case "read": return "Read this screen"
        case "open": return "Open it"
        default: return s.op
        }
    }

    private func load() async {
        do { skills = try await API.shared.skills(); error = nil }
        catch { self.error = error.localizedDescription }
    }

    private func run(_ k: TaughtSkill) async {
        running = k.id; defer { running = nil }
        do {
            let r = try await API.shared.runSkill(k.id)
            outcome[k.id] = r.status == "done"
                ? (true, "Done. \(r.handedIn) brought in as a private notice.")
                : (false, "Stopped: " + (r.stopped ?? "it needs you"))
            if let fresh = try? await API.shared.skills() { skills = fresh }
        } catch { outcome[k.id] = (false, error.localizedDescription) }
    }

    private func forget(_ k: TaughtSkill) async {
        do { try await API.shared.forgetSkill(k.id); skills?.removeAll { $0.id == k.id } }
        catch { self.error = error.localizedDescription }
    }
}

#if DEBUG
extension PreviewData {
    static let skills: [TaughtSkill] = decode("""
    [{"id":"f4000000-0000-0000-0000-000000000001","title":"School announcements","kind":"phone","target":"com.myclassboard.parent","steps":[{"op":"open"},{"op":"tap","text":"Announcements"},{"op":"read"}],"runs":6,"last_run_at":"\(day(-1))T07:30:00+05:30","last_outcome":"done"},
     {"id":"f4000000-0000-0000-0000-000000000002","title":"Library due dates","kind":"web","target":"https://library.example.org/account","steps":[{"op":"tap","text":"My loans"},{"op":"swipe","direction":"up"},{"op":"read"}],"runs":1,"last_run_at":"\(day(-4))T18:00:00+05:30","last_outcome":"step 1: “My loans” is not on the screen"}]
    """)
}

#Preview("Skills") { NavigationStack { SkillsView(preview: PreviewData.skills) } }
#Preview("Skills · dark, empty") { NavigationStack { SkillsView(preview: []) }.preferredColorScheme(.dark) }
#endif
