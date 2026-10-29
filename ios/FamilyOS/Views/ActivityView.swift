import SwiftUI

/// What was done in the household, as receipts: what was read, who approved, what changed. Where it can honestly be taken back (nothing has
/// changed since), a button does it. A guardian sees everyone's; anyone else only their own.
struct ActivityView: View {
    @State private var items: [ActivityItem] = []
    @State private var loaded = false
    @State private var error: String?
    @State private var open: Int?
    @State private var busy: Int?
    @State private var undone = 0
    @State private var more = true
    private let isSample: Bool

    init() { isSample = false }

    /// Rows from data in hand, for previews: nothing is fetched.
    init(sample: [ActivityItem]) {
        _items = State(initialValue: sample)
        _loaded = State(initialValue: true)
        isSample = true
    }

    var body: some View {
        List {
            Section {
                Text("Every action as a receipt. Tap one to see what was read and who approved it. Undo appears only when nothing has changed since.")
                    .font(Theme.font(13)).foregroundStyle(Theme.ink3)
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets(top: 0, leading: Spacing.xs, bottom: 0, trailing: Spacing.xs))
            }
            if !loaded && error == nil {
                LoadingRows(count: 4).listRowBackground(Color.clear).listRowInsets(EdgeInsets())
            } else if loaded && items.isEmpty && error == nil {
                EmptyState(symbol: "clock.arrow.circlepath", title: "Nothing yet",
                           text: "When FamilyOS or someone in the household accepts a date, hands something over or marks it handled, it shows here.", action: nil)
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets())
            }
            if !items.isEmpty {
                Section {
                    ForEach(items) { item in row(item) }
                    if more && !isSample {
                        Button("Older") { Task { await older() } }.font(Theme.font(14, .medium))
                    }
                }
            }
            if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Activity")
        .navigationBarTitleDisplayMode(.inline)
        .sensoryFeedback(.success, trigger: undone)
        .refreshable { await load() }
        .task { await load() }
    }

    @ViewBuilder private func row(_ item: ActivityItem) -> some View {
        VStack(alignment: .leading, spacing: Spacing.xs) {
            Button { open = open == item.id ? nil : item.id } label: {
                VStack(alignment: .leading, spacing: 2) {
                    Text(item.said).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink).multilineTextAlignment(.leading)
                    Text("\(item.who) · \(Format.stamp.string(from: item.at))").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                }
            }
            .buttonStyle(.plain)
            .accessibilityHint(open == item.id ? "Hide the receipt" : "Show the receipt")
            if open == item.id {
                VStack(alignment: .leading, spacing: 4) {
                    if let s = item.receipt.inferred { line("Read", s) }
                    if let s = item.receipt.observed { line("About", s) }
                    if let s = item.receipt.rule { line("Why", s) }
                    if let s = item.receipt.approvedBy { line("Approved by", s) }
                }
                .padding(.top, 2)
            }
            if let undo = item.undo {
                Button { Task { await take(item) } } label: {
                    Text(busy == item.id ? "…" : undo.label).font(Theme.font(13, .semibold))
                }
                .buttonStyle(.bordered).tint(Theme.primary).disabled(busy != nil)
                .accessibilityLabel("Undo: \(item.said). \(undo.label)")
            }
        }
        .padding(.vertical, 2)
    }

    private func line(_ k: String, _ v: String) -> some View {
        HStack(alignment: .top, spacing: Spacing.xs) {
            Text(k).font(Theme.font(12, .semibold)).foregroundStyle(Theme.ink3).frame(width: 78, alignment: .leading)
            Text(v).font(Theme.font(12)).foregroundStyle(Theme.ink2)
        }
    }

    private func load() async {
        guard !isSample else { return }
        do {
            let page = try await API.shared.activity()
            items = page; more = page.count >= 50; error = nil
        } catch { self.error = error.localizedDescription }
        loaded = true
    }

    private func older() async {
        guard let last = items.last else { return }
        do {
            let page = try await API.shared.activity(before: last.id)
            items += page.filter { p in !items.contains { $0.id == p.id } }
            more = page.count >= 50
        } catch { self.error = error.localizedDescription }
    }

    private func take(_ item: ActivityItem) async {
        if isSample { items.removeAll { $0.id == item.id }; return }
        busy = item.id; defer { busy = nil }
        do { _ = try await API.shared.undoActivity(item.id); undone += 1; error = nil; await load() } catch { self.error = error.localizedDescription }
    }
}
