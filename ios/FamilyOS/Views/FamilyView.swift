import SwiftUI

/// Everything about one person on one page.
struct PersonView: View {
    @EnvironmentObject var session: Session
    let member: Member
    @State private var notices: [InboxRow] = []
    @State private var brief: Brief?
    @State private var docs: [Document] = []

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack(spacing: 14) {
                    Avatar(member: member, size: 72)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(member.displayName).font(Theme.font(24, .medium, .serif)).foregroundStyle(Theme.ink)
                        Text(member.isChild ? [member.school, member.classLabel.map { "class \($0)" }].compactMap { $0 }.joined(separator: ", ") : member.role.capitalized).font(Theme.font(13)).foregroundStyle(Theme.ink3)
                    }
                }
                let tagged = Set(notices.filter { $0.subjectMemberIds.contains(member.id) }.map(\.id))
                let coming = (brief?.items ?? []).filter { i in i.dueDate != nil && (i.subjectMemberId == member.id || i.subjectName == member.displayName || (i.artifactId.map(tagged.contains) ?? false)) }
                Heading(title: "Coming up")
                if coming.isEmpty { Card { Text("Nothing dated.").foregroundStyle(Theme.ink3) } }
                else { Card(padding: 6) { VStack(spacing: 0) { ForEach(coming.prefix(10)) { i in NavigationLink(value: i) { BriefLine(item: i) }.buttonStyle(.plain) } } } }
                let held = docs.filter { $0.holderMemberId == member.id }
                if !held.isEmpty {
                    Heading(title: "Documents")
                    Card(padding: 6) { VStack(spacing: 0) { ForEach(held) { d in NavigationLink(value: d.artifactId) { DocumentRow(d: d).padding(8) }.buttonStyle(.plain) } } }
                }
                // Mail to an adult's own address names them, so without this every
                // promo and newsletter would be on their page.
                let named = notices.filter { $0.subjectMemberIds.contains(member.id) && $0.isAboutPeople }
                Heading(title: "Names \(member.displayName.split(separator: " ").first.map(String.init) ?? member.displayName)")
                if named.isEmpty { Card { Text("No notice names them yet.").foregroundStyle(Theme.ink3) } }
                else { Card(padding: 6) { VStack(spacing: 0) { ForEach(named.prefix(30)) { r in NavigationLink(value: r) { InboxRowView(row: r, who: session.name(of: r.assignedTo)).padding(8) }.buttonStyle(.plain); Divider().padding(.leading, 48) } } } }
                BarSpace()
            }.padding(16)
        }
        .paper()
        .navigationBarTitleDisplayMode(.inline)
        .navigationDestination(for: InboxRow.self) { row in NoticeView(artifactId: row.id, title: row.title) }
        .navigationDestination(for: BriefItem.self) { i in
            if let id = i.artifactId { NoticeView(artifactId: id, title: i.title) } else { Card { Text(i.why) }.padding().paper() }
        }
        .navigationDestination(for: UUID.self) { id in NoticeView(artifactId: id, title: "Document") }
        .task {
            notices = (try? await API.shared.inbox(days: 90, limit: 300)) ?? []
            brief = try? await API.shared.brief()
            docs = (try? await API.shared.documents())?.documents ?? []
        }
    }
}

struct DocumentRow: View {
    let d: Document
    var detail: String {
        var parts = [d.label]
        if let tail = d.identifierTail { parts.append("…" + tail) }
        if let e = d.expiresOn { parts.append((d.status == "expired" ? "expired " : "valid until ") + Format.dayYear.string(from: e)) }
        return parts.joined(separator: " · ")
    }
    var body: some View {
        HStack(spacing: 10) {
            Glyph(symbol: "doc.text", tint: d.status == "ok" ? Space.travel.color : Theme.amber, size: 34)
            VStack(alignment: .leading, spacing: 2) {
                Text(d.title).foregroundStyle(Theme.ink).lineLimit(1)
                Text(detail).font(.caption).foregroundStyle(d.status == "ok" ? Theme.ink3 : Theme.amber)
            }
            Spacer()
        }
    }
}
