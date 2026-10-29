import SwiftUI

/// A parent's consent for FamilyOS to keep a child's household records, and the declaration that they are the child's parent or lawful guardian.
/// Withdrawing a consent erases everything that names the child (the child stays a member), so it takes two steps and says exactly that first.
struct ConsentsView: View {
    @EnvironmentObject var session: Session
    @State private var consents: [ChildConsent] = []
    @State private var loaded = false
    @State private var error: String?
    @State private var giving: Member?
    @State private var withdrawing: ChildConsent?
    @State private var notice: String?
    @State private var changed = 0
    private let isSample: Bool

    init() { isSample = false }
    init(sample: [ChildConsent]) { _consents = State(initialValue: sample); _loaded = State(initialValue: true); isSample = true }

    private var isGuardian: Bool { session.member?.role == "guardian" }
    private func name(_ id: UUID) -> String { session.members.first { $0.id == id }?.displayName ?? "A child" }
    private var withoutConsent: [Member] { session.members.filter { m in m.isChild && !consents.contains { $0.subjectMemberId == m.id && $0.isActive } } }

    var body: some View {
        List {
            Section {
                Text("FamilyOS keeps nothing about a child until a parent or lawful guardian has consented. Each consent is kept as the record that it was given, and when it ended.")
                    .font(Theme.font(13)).foregroundStyle(Theme.ink3)
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets(top: 0, leading: Spacing.xs, bottom: 0, trailing: Spacing.xs))
            }
            if !loaded && error == nil { LoadingRows(count: 3).listRowBackground(Color.clear).listRowInsets(EdgeInsets()) }
            Section("Given") {
                ForEach(consents) { c in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(name(c.subjectMemberId)).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                        Text(c.isActive ? "Active since \(Format.dayYear.string(from: c.grantedAt))" : "Withdrawn \(Format.dayYear.string(from: c.withdrawnAt ?? c.grantedAt))")
                            .font(Theme.font(12)).foregroundStyle(c.isActive ? Theme.success : Theme.ink3)
                        Text("\(c.purpose.replacingOccurrences(of: "_", with: " ")) · notice \(c.noticeVersion) · \(c.verificationMethod.replacingOccurrences(of: "_", with: " "))")
                            .font(Theme.font(12)).foregroundStyle(Theme.ink3)
                        if let d = c.guardianDeclaredAt { Text("Declared a parent or lawful guardian on \(Format.dayYear.string(from: d))").font(Theme.font(12)).foregroundStyle(Theme.ink3) }
                        if isGuardian && c.isActive {
                            Button("Withdraw…", role: .destructive) { withdrawing = c }.font(Theme.font(13, .medium)).buttonStyle(.borderless)
                        }
                    }
                    .padding(.vertical, 2)
                }
                if loaded && consents.isEmpty && error == nil { Text("No consent has been recorded.").font(Theme.font(13)).foregroundStyle(Theme.ink3) }
            }
            if isGuardian && !withoutConsent.isEmpty {
                Section {
                    ForEach(withoutConsent) { m in
                        Button { giving = m } label: { Label("Give consent for \(m.displayName)", systemImage: "checkmark.seal") }
                    }
                } header: { Text("No consent yet") } footer: { Text("Until it is given, nothing is recorded about that child.") }
            }
            if !isGuardian { Text("Only a guardian gives or withdraws consent.").font(Theme.font(13)).foregroundStyle(Theme.ink3).listRowBackground(Color.clear) }
            if let notice { Text(notice).font(Theme.font(13)).foregroundStyle(Theme.ink2).listRowBackground(Color.clear) }
            if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Consent for children")
        .navigationBarTitleDisplayMode(.inline)
        .sensoryFeedback(.success, trigger: changed)
        .refreshable { await load() }
        .task { await load() }
        .sheet(item: $giving) { child in GiveConsentSheet(child: child) { await load(); changed += 1 } }
        .sheet(item: $withdrawing) { c in WithdrawSheet(consent: c, childName: name(c.subjectMemberId)) { started in
            notice = "Erasure started (\(started.status)). Everything that names \(name(c.subjectMemberId)) is being removed."
            await load(); changed += 1
        } }
    }

    private func load() async {
        guard !isSample else { return }
        do { consents = try await API.shared.consents(); error = nil } catch { self.error = error.localizedDescription }
        loaded = true
    }
}

private struct GiveConsentSheet: View {
    @Environment(\.dismiss) private var dismiss
    let child: Member
    let saved: () async -> Void
    @State private var declared = false
    @State private var version = String(ISO8601DateFormatter().string(from: Date()).prefix(7))
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Toggle("I am \(child.displayName)'s parent or lawful guardian, and I consent to FamilyOS keeping their household records.", isOn: $declared)
                    TextField("Notice version", text: $version).textInputAutocapitalization(.never)
                } footer: { Text("This is recorded with the time you said it, as the evidence that consent was given. You can withdraw it any time; that erases what names \(child.displayName).") }
                if let error { Text(error).foregroundStyle(Theme.danger) }
            }
            .navigationTitle("Consent").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("Give consent") { Task { await save() } }.disabled(busy || !declared || version.isEmpty) }
            }
        }
    }

    private func save() async {
        busy = true; defer { busy = false }
        do { _ = try await API.shared.grantConsent(for: child.id, notice: version, declared: declared); await saved(); dismiss() }
        catch { self.error = error.localizedDescription }
    }
}

/// The second step: what will go, then the child's name typed. Withdrawing cannot be undone.
private struct WithdrawSheet: View {
    @Environment(\.dismiss) private var dismiss
    let consent: ChildConsent
    let childName: String
    let started: (ErasureStarted) async -> Void
    @State private var typed = ""
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("What happens") {
                    Text("Everything that names \(childName) is erased: notices, dates, notes and anything read about them. \(childName) stays a member of the household. The record that consent was given, and that it ended, is kept.")
                    Text("This cannot be undone.").foregroundStyle(Theme.danger)
                }
                Section("Type \(childName)'s name to confirm") { TextField(childName, text: $typed).autocorrectionDisabled() }
                if let error { Text(error).foregroundStyle(Theme.danger) }
            }
            .navigationTitle("Withdraw consent").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .destructiveAction) {
                    Button("Withdraw and erase", role: .destructive) { Task { await go() } }
                        .disabled(busy || typed.trimmingCharacters(in: .whitespaces).caseInsensitiveCompare(childName) != .orderedSame)
                }
            }
        }
    }

    private func go() async {
        busy = true; defer { busy = false }
        do { let e = try await API.shared.withdrawConsent(consent.id); await started(e); dismiss() }
        catch { self.error = error.localizedDescription }
    }
}
