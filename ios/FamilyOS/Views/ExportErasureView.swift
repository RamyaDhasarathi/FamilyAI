import SwiftUI

/// Taking everything with you, and the two erasures. An export is made for the request and never kept. Erasing cannot be undone, so each takes two
/// steps: what will go, then the name typed. Only a guardian erases.
struct ExportErasureView: View {
    @EnvironmentObject var session: Session
    @State private var householdName = ""
    @State private var exported: URL?
    @State private var exportedLabel = ""
    @State private var busy = false
    @State private var error: String?
    @State private var erasingChild: Member?
    @State private var erasingHousehold = false
    @State private var notice: String?

    private var isGuardian: Bool { session.member?.role == "guardian" }
    private var kids: [Member] { session.members.filter { $0.isChild } }

    var body: some View {
        List {
            Section {
                Button { Task { await export(nil, label: "Your export") } } label: { Label(busy ? "Preparing…" : "Export what I can see", systemImage: "square.and.arrow.up") }.disabled(busy)
                if isGuardian {
                    ForEach(kids) { k in
                        Button { Task { await export(k.id, label: "\(k.displayName)'s records") } } label: { Label("Export \(k.displayName)'s records", systemImage: "person.crop.square") }.disabled(busy)
                    }
                }
                if let exported { ShareLink(item: exported) { Label("Share \(exportedLabel)", systemImage: "arrow.up.doc") } }
            } header: { Text("Take it with you") } footer: {
                Text("A zip of the originals, a readable page for each notice, and the same as data. It is built for this request and not stored.")
            }
            if isGuardian {
                Section {
                    ForEach(kids) { k in
                        Button(role: .destructive) { erasingChild = k } label: { Label("Erase \(k.displayName)'s data…", systemImage: "trash") }
                    }
                    Button(role: .destructive) { erasingHousehold = true } label: { Label("Erase the whole household…", systemImage: "trash.slash") }
                } header: { Text("Erase") } footer: { Text("Cannot be undone. You are asked to type a name before anything is erased.") }
            } else {
                Text("Only a guardian can erase.").font(Theme.font(13)).foregroundStyle(Theme.ink3).listRowBackground(Color.clear)
            }
            if let notice { Text(notice).font(Theme.font(13)).foregroundStyle(Theme.ink2).listRowBackground(Color.clear) }
            if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Export and erase")
        .navigationBarTitleDisplayMode(.inline)
        .task { if isGuardian, let h = try? await API.shared.household() { householdName = h.name } }
        .sheet(item: $erasingChild) { kid in
            TypedErase(title: "Erase \(kid.displayName)'s data",
                       what: "Every notice, date, note and record that names \(kid.displayName) is erased, and \(kid.displayName) is removed from the household. Their export, if you want one, has to be made first.",
                       confirm: kid.displayName) {
                let e = try await API.shared.eraseChild(kid.id)
                notice = "Erasure started (\(e.status)). \(kid.displayName)'s data is being removed."
                await session.refreshHousehold()
            }
        }
        .sheet(isPresented: $erasingHousehold) {
            TypedErase(title: "Erase the whole household",
                       what: "Everything, for everyone: every original, notice, record and the activity log is deleted, and the household's key is destroyed. Everyone is signed out at once, on every phone and the web. There is no way back.",
                       confirm: householdName) {
                _ = try await API.shared.eraseHousehold(confirmName: householdName)
                await session.signOut()
            }
        }
    }

    private func export(_ member: UUID?, label: String) async {
        busy = true; defer { busy = false }
        do { exported = try await API.shared.exportFile(of: member); exportedLabel = label; error = nil } catch { self.error = error.localizedDescription }
    }
}

/// Step two of an erasure: say exactly what goes, then ask for the name.
private struct TypedErase: View {
    @Environment(\.dismiss) private var dismiss
    let title: String
    let what: String
    let confirm: String
    let run: () async throws -> Void
    @State private var typed = ""
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("What will happen") {
                    Text(what)
                    Text("This cannot be undone.").foregroundStyle(Theme.danger)
                }
                Section("Type \(confirm) to confirm") { TextField(confirm, text: $typed).autocorrectionDisabled().textInputAutocapitalization(.never) }
                if let error { Text(error).foregroundStyle(Theme.danger) }
            }
            .navigationTitle(title).navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .destructiveAction) {
                    Button("Erase", role: .destructive) { Task { await go() } }
                        .disabled(busy || confirm.isEmpty || typed.trimmingCharacters(in: .whitespaces) != confirm)
                }
            }
        }
    }

    private func go() async {
        busy = true; defer { busy = false }
        do { try await run(); dismiss() } catch { self.error = error.localizedDescription }
    }
}
