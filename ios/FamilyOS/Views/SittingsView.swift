import SwiftUI

/// A sitting: you sign in to a site yourself in a browser and FamilyOS collects the pages you open. Nothing is kept until you pick it, no password
/// is taken, and what you do not pick is destroyed when the sitting ends.
struct SittingsView: View {
    @Environment(\.openURL) private var openURL
    @State private var sittings: [Sitting] = []
    @State private var loaded = false
    @State private var error: String?
    @State private var starting = false
    @State private var changed = 0
    private let isSample: Bool

    init() { isSample = false }
    init(sample: [Sitting]) { _sittings = State(initialValue: sample); _loaded = State(initialValue: true); isSample = true }

    var body: some View {
        List {
            Section {
                Text("Open a sitting, sign in to the site yourself, and the pages you visit are collected for you to read. You choose what to keep.")
                    .font(Theme.font(13)).foregroundStyle(Theme.ink3)
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets(top: 0, leading: Spacing.xs, bottom: 0, trailing: Spacing.xs))
            }
            if !loaded && error == nil { LoadingRows(count: 3).listRowBackground(Color.clear).listRowInsets(EdgeInsets()) }
            Section {
                ForEach(sittings) { s in
                    NavigationLink { SittingPagesView(sitting: s) } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(s.label).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                            Text("\(s.isOpen ? "Open until \(Format.clock.string(from: s.expiresAt))" : s.state.capitalized) · \(s.allowHosts.joined(separator: ", "))")
                                .font(Theme.font(12)).foregroundStyle(Theme.ink3)
                        }
                    }
                }
                if loaded && sittings.isEmpty && error == nil { Text("No sittings yet.").font(Theme.font(13)).foregroundStyle(Theme.ink3) }
                Button { starting = true } label: { Label("Start a sitting", systemImage: "plus") }
            }
            if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Sign-in sittings")
        .navigationBarTitleDisplayMode(.inline)
        .sensoryFeedback(.success, trigger: changed)
        .refreshable { await load() }
        .task { await load() }
        .sheet(isPresented: $starting) {
            StartSittingSheet { sitting in
                await load(); changed += 1
                if let live = sitting.liveUrl, let url = URL(string: live) { openURL(url) }
            }
        }
    }

    private func load() async {
        guard !isSample else { return }
        do { sittings = try await API.shared.sittings(); error = nil } catch { self.error = error.localizedDescription }
        loaded = true
    }
}

private struct StartSittingSheet: View {
    @Environment(\.dismiss) private var dismiss
    let started: (Sitting) async -> Void
    @State private var label = ""
    @State private var host = ""
    @State private var minutes = 30
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("A name for it", text: $label)
                    TextField("Site (example.com)", text: $host).keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                    Stepper("Open for \(minutes) minutes", value: $minutes, in: 10...180, step: 10)
                } footer: { Text("Only pages on this site are collected. The browser opens for you to sign in; FamilyOS never sees your password.") }
                if let error { Text(error).foregroundStyle(Theme.danger) }
            }
            .navigationTitle("Start a sitting").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("Start") { Task { await go() } }.disabled(busy || label.isEmpty || host.isEmpty) }
            }
        }
    }

    private func go() async {
        busy = true; defer { busy = false }
        let clean = host.trimmingCharacters(in: .whitespaces).lowercased().replacingOccurrences(of: "https://", with: "").replacingOccurrences(of: "/", with: "")
        do { let s = try await API.shared.beginSitting(label: label.trimmingCharacters(in: .whitespaces), hosts: [clean], minutes: minutes); await started(s); dismiss() }
        catch { self.error = error.localizedDescription }
    }
}

/// What a sitting collected. Keeping a page puts it in the record; discarding destroys it. Ending the sitting destroys whatever was not picked.
struct SittingPagesView: View {
    let sitting: Sitting
    @State private var pages: [SittingPage] = []
    @State private var loaded = false
    @State private var error: String?
    @State private var ending = false
    @State private var changed = 0
    @State private var open: UUID?
    private let isSample: Bool

    init(sitting: Sitting) { self.sitting = sitting; isSample = false }
    init(sitting: Sitting, sample: [SittingPage]) { self.sitting = sitting; _pages = State(initialValue: sample); _loaded = State(initialValue: true); isSample = true }

    var body: some View {
        List {
            if !loaded && error == nil { LoadingRows(count: 3).listRowBackground(Color.clear).listRowInsets(EdgeInsets()) }
            else if loaded && pages.isEmpty && error == nil {
                EmptyState(symbol: "doc.text.magnifyingglass", title: "Nothing collected", text: "Pages appear here as you open them in the browser.", action: nil)
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets())
            }
            ForEach(pages) { p in
                VStack(alignment: .leading, spacing: Spacing.xs) {
                    Button { open = open == p.id ? nil : p.id } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(p.title.isEmpty ? p.url : p.title).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink).multilineTextAlignment(.leading)
                            Text("\(p.url) · \(p.bytes) bytes\(p.decision.map { " · \($0)" } ?? "")").font(Theme.font(12)).foregroundStyle(Theme.ink3).lineLimit(1)
                        }
                    }.buttonStyle(.plain)
                    if open == p.id { Text(String(p.text.prefix(1500))).font(Theme.font(12)).foregroundStyle(Theme.ink2) }
                    if sitting.isOpen && p.decision == nil {
                        HStack {
                            Button("Keep") { Task { await decide(p, keep: true) } }.buttonStyle(.borderedProminent).tint(Theme.primary)
                            Button("Discard", role: .destructive) { Task { await decide(p, keep: false) } }.buttonStyle(.bordered)
                        }.font(Theme.font(13, .semibold))
                    }
                }
                .padding(.vertical, 2)
            }
            if sitting.isOpen {
                Section { Button("End the sitting…", role: .destructive) { ending = true } } footer: { Text("Pages you did not keep are destroyed when it ends.") }
            }
            if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle(sitting.label)
        .navigationBarTitleDisplayMode(.inline)
        .sensoryFeedback(.success, trigger: changed)
        .refreshable { await load() }
        .task { await load() }
        .confirmationDialog("End this sitting?", isPresented: $ending, titleVisibility: .visible) {
            Button("End it and destroy what was not kept", role: .destructive) { Task { await finish() } }
        } message: { Text("Pages you have not kept are destroyed and cannot be brought back.") }
    }

    private func load() async {
        guard !isSample else { return }
        do { pages = try await API.shared.sittingPages(sitting.id); error = nil } catch { self.error = error.localizedDescription }
        loaded = true
    }

    private func decide(_ p: SittingPage, keep: Bool) async {
        if isSample { pages.removeAll { $0.id == p.id }; return }
        do { if keep { try await API.shared.keepPage(p.id) } else { try await API.shared.discardPage(p.id) }; changed += 1; await load() }
        catch { self.error = error.localizedDescription }
    }

    private func finish() async {
        if isSample { return }
        do { try await API.shared.finishSitting(sitting.id); changed += 1; await load() } catch { self.error = error.localizedDescription }
    }
}
