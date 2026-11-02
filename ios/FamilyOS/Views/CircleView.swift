import SwiftUI

/// Who has been handed part of the household's view, and for how long. A guardian hands out one of the named scopes (pickups only, one child's
/// school notices, the emergency card); each ends by itself, and anyone can end one early. The list is open to every member: who can see what is
/// yours to know.
struct CircleView: View {
    @EnvironmentObject var session: Session
    @State private var grants: [HouseholdGrant] = []
    @State private var presets: [CirclePreset] = []
    @State private var loaded = false
    @State private var error: String?
    @State private var handing = false
    @State private var ending: HouseholdGrant?
    @State private var changed = 0
    private let isSample: Bool

    init() { isSample = false }
    init(grants: [HouseholdGrant], presets: [CirclePreset]) {
        _grants = State(initialValue: grants); _presets = State(initialValue: presets); _loaded = State(initialValue: true); isSample = true
    }

    private var isGuardian: Bool { session.member?.role == "guardian" }

    var body: some View {
        List {
            Section {
                Text("A grant shows someone the obligations you choose, never the notices they were read from, and ends on the date shown.")
                    .font(Theme.font(13)).foregroundStyle(Theme.ink3)
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets(top: 0, leading: Spacing.xs, bottom: 0, trailing: Spacing.xs))
            }
            if !loaded && error == nil { LoadingRows(count: 3).listRowBackground(Color.clear).listRowInsets(EdgeInsets()) }
            Section {
                ForEach(grants) { g in
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(g.granteeName)\(g.subjectName.map { " · about \($0)" } ?? "")").font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                        Text(g.reason).font(Theme.font(13)).foregroundStyle(Theme.ink2)
                        Text("Can: \(g.actions.joined(separator: ", ")) · until \(Format.dayYear.string(from: g.expiresAt)) · given by \(g.grantedByName)")
                            .font(Theme.font(12)).foregroundStyle(Theme.ink3)
                        if isGuardian || g.grantedByName == session.member?.displayName {
                            Button("End now", role: .destructive) { ending = g }.font(Theme.font(13, .medium)).buttonStyle(.borderless)
                        }
                    }
                    .padding(.vertical, 2)
                }
                if loaded && grants.isEmpty && error == nil { Text("Nobody has been handed anything.").font(Theme.font(13)).foregroundStyle(Theme.ink3) }
                if isGuardian && !presets.isEmpty { Button { handing = true } label: { Label("Hand someone a scope", systemImage: "plus") } }
            } header: { Text("Handed out") }
            if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Circle and grants")
        .navigationBarTitleDisplayMode(.inline)
        .sensoryFeedback(.success, trigger: changed)
        .refreshable { await load() }
        .task { await load() }
        .sheet(isPresented: $handing) { HandSheet(presets: presets) { await load(); changed += 1 } }
        .confirmationDialog("End this grant now?", isPresented: Binding(get: { ending != nil }, set: { if !$0 { ending = nil } }), titleVisibility: .visible, presenting: ending) { g in
            Button("End it for \(g.granteeName)", role: .destructive) { Task { await end(g) } }
        } message: { g in
            Text("\(g.granteeName) stops seeing \(g.reason.lowercased()) straight away. You can hand it out again.")
        }
    }

    private func load() async {
        guard !isSample else { return }
        do {
            grants = try await API.shared.grants()
            if isGuardian { presets = try await API.shared.circlePresets() }
            error = nil
        } catch { self.error = error.localizedDescription }
        loaded = true
    }

    private func end(_ g: HouseholdGrant) async {
        if isSample { grants.removeAll { $0.id == g.id }; return }
        do { try await API.shared.revokeGrant(g.id); changed += 1; await load() } catch { self.error = error.localizedDescription }
    }
}

private struct HandSheet: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) private var dismiss
    let presets: [CirclePreset]
    let done: () async -> Void
    @State private var preset: CirclePreset?
    @State private var person: UUID?
    @State private var child: UUID?
    @State private var days = 0
    @State private var busy = false
    @State private var error: String?

    private var others: [Member] { session.members.filter { !$0.isChild && $0.id != session.member?.id } }
    private var kids: [Member] { session.members.filter { $0.isChild } }
    private var needsChild: Bool { preset?.needsChild == true }
    private var ready: Bool { preset != nil && person != nil && (!needsChild || child != nil) }

    var body: some View {
        NavigationStack {
            Form {
                Section("Scope") {
                    ForEach(presets) { p in
                        Button { preset = p; days = p.days } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(p.label).foregroundStyle(Theme.ink)
                                    Text("Can: \(p.actions.joined(separator: ", ")) · \(p.days) days").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                                }
                                Spacer()
                                if preset?.key == p.key { Image(systemName: "checkmark").foregroundStyle(Theme.primary) }
                            }
                        }
                    }
                }
                Section("To") {
                    Picker("Person", selection: $person) { Text("Choose").tag(UUID?.none); ForEach(others) { Text($0.displayName).tag(UUID?.some($0.id)) } }
                    if needsChild { Picker("About which child", selection: $child) { Text("Choose").tag(UUID?.none); ForEach(kids) { Text($0.displayName).tag(UUID?.some($0.id)) } } }
                    if preset != nil { Stepper("For \(days) days", value: $days, in: 1...365) }
                }
                if let preset, let p = others.first(where: { $0.id == person }) {
                    Section { Text("\(p.displayName) will be able to \(preset.actions.joined(separator: ", ")) on the obligations in this scope for \(days) days. It ends by itself, and you can end it sooner.") }
                }
                if let error { Text(error).foregroundStyle(Theme.danger) }
            }
            .navigationTitle("Hand out a scope").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("Hand out") { Task { await save() } }.disabled(busy || !ready) }
            }
        }
    }

    private func save() async {
        guard let preset, let person else { return }
        busy = true; defer { busy = false }
        do { _ = try await API.shared.grantPreset(preset.key, to: person, about: needsChild ? child : nil, days: days); await done(); dismiss() }
        catch { self.error = error.localizedDescription }
    }
}
