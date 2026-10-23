import SwiftUI

/// Every notice the member can see, newest first. The same rows the
/// console's Inbox shows, with the same state: to do, done, information.
struct InboxView: View {
    @EnvironmentObject var session: Session
    @State private var rows: [InboxRow] = []
    @State private var error: String?
    @State private var search = ""
    @State private var onlyOpen = false
    @State private var showAdd = false

    /// Folded away unless searched for: bank alerts are lines in Money, promos and newsletters are noise.
    private static let quiet: Set<String> = InboxRow.quietCategories
    private var folded: Int { rows.filter { Self.quiet.contains($0.category) }.count }
    var shown: [InboxRow] {
        rows.filter { r in
            (!onlyOpen || r.state == "todo") &&
            (!search.isEmpty || !Self.quiet.contains(r.category)) &&
            (search.isEmpty || r.title.localizedCaseInsensitiveContains(search) || r.fromLabel.localizedCaseInsensitiveContains(search)
             || r.preview.joined(separator: " ").localizedCaseInsensitiveContains(search))
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                ErrorLine(text: error)
                HStack(spacing: 8) {
                    Button { onlyOpen = false } label: { Chip(text: "Everything", on: !onlyOpen) }.buttonStyle(.plain)
                    Button { onlyOpen = true } label: { Chip(text: "Open", on: onlyOpen) }.buttonStyle(.plain)
                    Spacer()
                }
                if rows.isEmpty && error == nil { EmptyState(symbol: "tray", title: "Nothing has arrived yet", text: "Share something from any app, mail the household's address, or add a notice here.", action: ("Add a notice", { showAdd = true })) }
                Card(padding: 6) {
                    VStack(spacing: 0) {
                        ForEach(shown) { row in
                            NavigationLink(value: row) { InboxRowView(row: row, who: session.name(of: row.assignedTo)).padding(8) }.buttonStyle(.plain)
                            if row.id != shown.last?.id { Divider().padding(.leading, 48) }
                        }
                    }
                }
                if folded > 0 && search.isEmpty {
                    Text("\(folded) bank alert\(folded == 1 ? "" : "s"), promo\(folded == 1 ? "" : "s") or newsletter\(folded == 1 ? "" : "s") folded away. Bank lines count in Money; search to see them.")
                        .font(Theme.font(12)).foregroundStyle(Theme.ink3).padding(.horizontal, 4)
                }
                BarSpace()
            }.padding(16)
        }
        .paper()
        .navigationTitle("Inbox")
        .navigationBarTitleDisplayMode(.large)
        .searchable(text: $search, prompt: "Headline, sender, words")
        .toolbar { ToolbarItem(placement: .primaryAction) { Button { showAdd = true } label: { Image(systemName: "plus") }.accessibilityLabel("Add a notice") } }
        .sheet(isPresented: $showAdd, onDismiss: { Task { await load() } }) { AddNoticeView() }
        .navigationDestination(for: InboxRow.self) { row in NoticeView(artifactId: row.id, title: row.title) }
        .refreshable { await load() }
        .task { await load(); if Debug.string("add") != nil { showAdd = true } }
    }

    private func load() async {
        do { rows = try await API.shared.inbox(); error = nil }
        catch { self.error = error.localizedDescription }
    }
}

struct InboxRowView: View {
    let row: InboxRow
    let who: String?
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Glyph(symbol: icon, tint: tint, size: 34)
            VStack(alignment: .leading, spacing: 2) {
                Text(row.title).foregroundStyle(Theme.ink).lineLimit(2)
                HStack(spacing: 6) {
                    Text(row.fromLabel).lineLimit(1)
                    Text("·")
                    Text(Format.day.string(from: row.receivedAt))
                    Text("·")
                    Label(row.visibility == "shared" ? "Household" : "Private", systemImage: row.visibility == "shared" ? "person.2" : "lock").font(.caption2).labelStyle(.titleAndIcon)
                }.font(.caption).foregroundStyle(.secondary)
                if let next = row.nextDate, row.state == "todo" {
                    Text("Next: \(Format.day.string(from: next))" + (row.open > 1 ? " and \(row.open - 1) more" : "")).font(.caption).foregroundStyle(Theme.ink2)
                } else if let note = row.handledNote {
                    Text(note).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                } else if let who {
                    Text("With \(who)" + (row.assignedNote.map { ": \($0)" } ?? "")).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
            }
            Spacer(minLength: 0)
            if row.state == "todo", row.open > 0 { Text("\(row.open)").font(Theme.font(11, .semibold)).padding(.horizontal, 7).padding(.vertical, 2).background(Theme.amber.opacity(0.2)).foregroundStyle(Theme.ink2).clipShape(Capsule()) }
        }
    }

    var icon: String {
        if row.isPicture { return "photo" }
        switch row.channel {
        case "gmail", "email": return "envelope"
        case "telegram", "whatsapp": return "bubble.left"
        case "share": return "square.and.arrow.up"
        default: return "doc"
        }
    }
    var tint: Color {
        switch row.state { case "todo": return Space.of(category: row.category).color; case "done": return Theme.green; default: return Theme.ink3 }
    }
}
