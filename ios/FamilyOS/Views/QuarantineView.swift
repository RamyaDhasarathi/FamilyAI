import SwiftUI

/// Things that arrived from a sender FamilyOS does not know. Nothing here has been read. A guardian lets it in (it is read and its sender is
/// remembered) or turns it away.
struct QuarantineView: View {
    @EnvironmentObject var session: Session
    @State private var items: [HeldItem] = []
    @State private var loaded = false
    @State private var error: String?
    @State private var busy: UUID?
    @State private var done = 0

    var body: some View {
        List {
            if session.member?.role != "guardian" {
                EmptyState(symbol: "lock.shield", title: "For a guardian", text: "A guardian decides what from an unknown sender is let in.", action: nil)
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets())
            } else {
                Section {
                    Text("These came from someone FamilyOS does not know, so none of it has been read. Let in what is yours; it is then read and that sender is remembered.")
                        .font(Theme.font(13)).foregroundStyle(Theme.ink3)
                        .listRowBackground(Color.clear).listRowInsets(EdgeInsets(top: 0, leading: Spacing.xs, bottom: 0, trailing: Spacing.xs))
                }
                if !loaded && error == nil {
                    LoadingRows(count: 3).listRowBackground(Color.clear).listRowInsets(EdgeInsets())
                } else if loaded && items.isEmpty && error == nil {
                    EmptyState(symbol: "checkmark.shield", title: "Nothing held", text: "Everything that arrived came from a sender you know.", action: nil)
                        .listRowBackground(Color.clear).listRowInsets(EdgeInsets())
                }
                ForEach(items) { item in
                    VStack(alignment: .leading, spacing: Spacing.xs) {
                        Text(item.headline).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                        Text("From \(item.sender) · \(item.channel) · \(Format.stamp.string(from: item.receivedAt))").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                        if let why = item.quarantineReason { Text(why).font(Theme.font(12)).foregroundStyle(Theme.ink3) }
                        HStack {
                            Button("Let it in") { Task { await accept(item) } }.buttonStyle(.borderedProminent).tint(Theme.primary)
                            Button("Turn away", role: .destructive) { Task { await reject(item) } }.buttonStyle(.bordered)
                        }
                        .font(Theme.font(13, .semibold)).disabled(busy != nil)
                    }
                    .padding(.vertical, 2)
                }
            }
            if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Held mail")
        .navigationBarTitleDisplayMode(.inline)
        .sensoryFeedback(.success, trigger: done)
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        guard session.member?.role == "guardian" else { loaded = true; return }
        do { items = try await API.shared.held(); error = nil } catch { self.error = error.localizedDescription }
        loaded = true
    }

    private func accept(_ item: HeldItem) async {
        busy = item.id; defer { busy = nil }
        do { try await API.shared.acceptHeld(item.id); done += 1; items.removeAll { $0.id == item.id }; error = nil } catch { self.error = error.localizedDescription }
    }

    private func reject(_ item: HeldItem) async {
        busy = item.id; defer { busy = nil }
        do { try await API.shared.rejectHeld(item.id); done += 1; items.removeAll { $0.id == item.id }; error = nil } catch { self.error = error.localizedDescription }
    }
}
