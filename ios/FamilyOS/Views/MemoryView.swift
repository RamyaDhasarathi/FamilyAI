import SwiftUI

/// What FamilyOS holds about the household, and why. Open one to see where it came from; say it is right, or (for a child's school) correct it.
struct MemoryView: View {
    @State private var facts: [MemoryFact]?
    @State private var error: String?

    var body: some View {
        List {
            Section {
                Text("These are the facts FamilyOS works from. None is a guess it keeps quiet about: each has its source, and you can correct or confirm it.")
                    .font(Theme.font(13)).foregroundStyle(Theme.ink3)
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets(top: 0, leading: Spacing.xs, bottom: 0, trailing: Spacing.xs))
            }
            if let facts {
                if facts.isEmpty {
                    EmptyState(symbol: "brain.head.profile", title: "Nothing held yet", text: "Set a child's school, or share a passport or a policy, and it shows here.", action: nil)
                        .listRowBackground(Color.clear).listRowInsets(EdgeInsets())
                }
                ForEach(facts) { f in
                    NavigationLink { MemoryFactView(fact: f) { await load() } } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(f.label).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                            Text(f.value).font(Theme.font(13)).foregroundStyle(Theme.ink2)
                            Text(f.lastVerified.map { "Confirmed " + Format.dayYear.string(from: $0) } ?? "Not confirmed yet")
                                .font(Theme.font(12)).foregroundStyle(Theme.ink3)
                        }
                    }
                }
            } else if error == nil { LoadingRows(count: 4).listRowBackground(Color.clear).listRowInsets(EdgeInsets()) }
            if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("What FamilyOS knows")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        do { facts = try await API.shared.memory(); error = nil } catch { self.error = error.localizedDescription }
    }
}

private struct MemoryFactView: View {
    @EnvironmentObject var session: Session
    @State var fact: MemoryFact
    let changed: () async -> Void
    @State private var steps: [String] = []
    @State private var school = ""
    @State private var classLabel = ""
    @State private var error: String?
    @State private var busy = false
    @State private var done = 0

    private var isGuardian: Bool { session.member?.role == "guardian" }

    var body: some View {
        List {
            Section {
                Text(fact.value).font(Theme.font(17, .medium))
                Text(fact.source.text).font(Theme.font(13)).foregroundStyle(Theme.ink2)
            } header: { Text(fact.label) }
            if let id = fact.source.artifactId {
                Section { NavigationLink { NoticeView(artifactId: id, title: fact.label) } label: { Label("Open the notice it was read from", systemImage: "doc.text") } }
            }
            Section("Why FamilyOS thinks so") {
                ForEach(steps, id: \.self) { Text($0).font(Theme.font(14)).foregroundStyle(Theme.ink2) }
            }
            Section {
                Button { Task { await verify() } } label: { Label("This is right", systemImage: "checkmark.seal") }.disabled(busy)
            } footer: { Text("Saying it is right moves the date it was last confirmed, and the date to look at it again.") }
            if fact.correctable && isGuardian {
                Section {
                    TextField("School", text: $school)
                    TextField("Class (optional)", text: $classLabel)
                    Button("Correct it") { Task { await correct() } }.disabled(busy || school.trimmingCharacters(in: .whitespaces).isEmpty)
                } header: { Text("Correct it") } footer: { Text("Recorded with the old value and who changed it.") }
            } else if let how = fact.howToCorrect {
                Section("To change it") { Text(how).font(Theme.font(13)).foregroundStyle(Theme.ink3) }
            }
            if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Why")
        .navigationBarTitleDisplayMode(.inline)
        .sensoryFeedback(.success, trigger: done)
        .task { await why() }
    }

    private func why() async {
        do { let w = try await API.shared.memoryWhy(fact.key); fact = w; steps = w.explanation ?? []; error = nil } catch { self.error = error.localizedDescription }
    }

    private func verify() async {
        busy = true; defer { busy = false }
        do { let w = try await API.shared.verifyMemory(fact.key); fact = w; steps = w.explanation ?? steps; done += 1; error = nil; await changed() } catch { self.error = error.localizedDescription }
    }

    private func correct() async {
        busy = true; defer { busy = false }
        do {
            let w = try await API.shared.correctMemory(fact.key, school: school.trimmingCharacters(in: .whitespaces), classLabel: classLabel.isEmpty ? nil : classLabel)
            fact = w; steps = w.explanation ?? steps; done += 1; error = nil; await changed()
        } catch { self.error = error.localizedDescription }
    }
}
