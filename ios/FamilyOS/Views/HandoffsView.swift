import SwiftUI

/// What you handed to someone and are waiting on, and what was handed to you. A hand-off nobody answers goes to the backup if one was named, else
/// the sender is told; this is where you see where each one stands.
struct HandoffsView: View {
    @State private var items: [Handoff] = []
    @State private var loaded = false
    @State private var error: String?
    private let isSample: Bool

    init() { isSample = false }
    init(sample: [Handoff]) { _items = State(initialValue: sample); _loaded = State(initialValue: true); isSample = true }

    private var forMe: [Handoff] { items.filter { $0.direction == "for_me" } }
    private var waiting: [Handoff] { items.filter { $0.direction == "waiting_on" } }

    var body: some View {
        List {
            if !loaded && error == nil { LoadingRows(count: 3).listRowBackground(Color.clear).listRowInsets(EdgeInsets()) }
            else if loaded && items.isEmpty && error == nil {
                EmptyState(symbol: "arrowshape.turn.up.right", title: "Nothing handed over",
                           text: "When you hand a notice to someone, or they hand one to you, it shows here until it is handled.", action: nil)
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets())
            }
            if !forMe.isEmpty { Section("Handed to you") { ForEach(forMe) { row($0, who: "From") } } }
            if !waiting.isEmpty {
                Section {
                    ForEach(waiting) { row($0, who: "To") }
                } header: { Text("You are waiting on") } footer: {
                    Text("If someone does not answer in time it moves to the backup you named, or you are told.")
                }
            }
            if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Handed over")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task { await load() }
    }

    private func row(_ h: Handoff, who: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(h.title).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
            Text("\(who) \(h.with ?? "someone") · \(h.state.capitalized) · since \(Format.day.string(from: h.since))\(h.hasBackup ? " · has a backup" : "")")
                .font(Theme.font(12)).foregroundStyle(Theme.ink3)
        }
        .padding(.vertical, 2)
    }

    private func load() async {
        guard !isSample else { return }
        do { items = try await API.shared.handoffs(); error = nil } catch { self.error = error.localizedDescription }
        loaded = true
    }
}

/// Who is carrying what: the hand-offs still open and what each adult handled in the last 30 days, then how the notices that arrived were divided.
/// Counted from the record, not from anything typed in, and not a judgement about anyone.
struct WorkloadView: View {
    @EnvironmentObject var session: Session
    @State private var adults: [AdultWorkload] = []
    @State private var load: HouseholdLoad?
    @State private var loaded = false
    @State private var error: String?
    private let isSample: Bool

    init() { isSample = false }
    init(adults: [AdultWorkload], load: HouseholdLoad) {
        _adults = State(initialValue: adults); _load = State(initialValue: load); _loaded = State(initialValue: true); isSample = true
    }

    var body: some View {
        List {
            if session.member?.isChild == true {
                EmptyState(symbol: "person.2", title: "For the adults", text: "How the household's work divides is shown to the adults.", action: nil)
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets())
            } else {
                if !loaded && error == nil { LoadingRows(count: 3).listRowBackground(Color.clear).listRowInsets(EdgeInsets()) }
                if !adults.isEmpty {
                    Section("Right now and this month") {
                        ForEach(adults) { a in
                            HStack {
                                Text(a.name).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                                Spacer()
                                Text("\(a.open) open · \(a.handled30d) handled").font(Theme.font(13)).foregroundStyle(Theme.ink3)
                            }
                        }
                    }
                }
                if let load {
                    Section {
                        ForEach(load.members) { m in
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Text(m.displayName).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                                    Spacer()
                                    Text("\(m.share)%").font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                                }
                                ProgressView(value: Double(min(max(m.share, 0), 100)), total: 100).tint(Theme.primary).accessibilityHidden(true)
                                Text("Carried \(m.carried) · noticed \(m.noticed) · decided \(m.decided) · acted on \(m.acted)").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                            }
                            .padding(.vertical, 2)
                        }
                        if load.undecided > 0 || load.missed > 0 {
                            Text("\(load.undecided) of \(load.total) notices are still undecided and \(load.missed) went by.").font(Theme.font(13)).foregroundStyle(Theme.ink2)
                        }
                    } header: { Text("The last \(load.days) days") } footer: { Text(load.note) }
                }
                if loaded && adults.isEmpty && load == nil && error == nil {
                    EmptyState(symbol: "person.2", title: "Nothing counted yet", text: "It fills in as notices arrive and are handled.", action: nil)
                        .listRowBackground(Color.clear).listRowInsets(EdgeInsets())
                }
                if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
            }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Who carries what")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await fetch() }
        .task { await fetch() }
    }

    private func fetch() async {
        guard !isSample, session.member?.isChild != true else { loaded = true; return }
        do {
            async let a = API.shared.workload(), l = API.shared.load()
            (adults, load) = try await (a, l)
            error = nil
        } catch { self.error = error.localizedDescription }
        loaded = true
    }
}
