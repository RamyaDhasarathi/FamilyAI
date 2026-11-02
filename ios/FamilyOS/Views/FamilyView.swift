import SwiftUI

/// Everything about one person on one page.
struct PersonView: View {
    @EnvironmentObject var session: Session
    let member: Member
    @State private var notices: [InboxRow] = []
    @State private var brief: Brief?
    @State private var docs: [Document] = []
    @State private var joining: MemberJoining?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack(spacing: 14) {
                    Avatar(member: member, size: 72)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(member.displayName).font(Theme.font(24, .medium, .serif)).foregroundStyle(Theme.ink)
                        Text(member.isChild ? [member.school, member.classLabel.map { "class \($0)" }].compactMap { $0 }.joined(separator: ", ") : member.role.capitalized).font(Theme.font(13)).foregroundStyle(Theme.ink3)
                        if !member.isChild && joining?.joined == false { Tag(text: "waiting to join", symbol: "hourglass", tint: Theme.warning).padding(.top, 2) }
                    }
                }
                if session.member?.role == "guardian" || member.id == session.member?.id {
                    NavigationLink { ProfileView(memberId: member.id) } label: {
                        Card {
                            HStack(spacing: Spacing.m) {
                                Image(systemName: "person.text.rectangle").foregroundStyle(Theme.ink2).frame(width: 24).accessibilityHidden(true)
                                Text("Profile").font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                                Spacer()
                                Text(member.isChild ? "Allergies, blood group" : "Number, work place, reach").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.ink3).accessibilityHidden(true)
                            }
                        }
                    }
                    .buttonStyle(.plain).accessibilityElement(children: .combine).accessibilityHint("Opens \(member.displayName)'s profile")
                }
                if !member.isChild && session.member?.role == "guardian" && member.id != session.member?.id {
                    InviteCard(member: member, joined: joining?.joined ?? true, invitedAt: joining?.invitedAt)
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
            joining = (try? await API.shared.joining())?[member.id]
        }
    }
}

/// A guardian's way to bring an adult in: a single-use sign-in link, also
/// emailed when the server has mail, shown here to copy or hand over in a
/// message. Asking again replaces the last link. The link is shown, never kept.
struct InviteCard: View {
    let member: Member
    let joined: Bool
    let invitedAt: Date?
    @State private var invitation: Invitation?
    @State private var error: String?
    @State private var busy = false
    @State private var copied = false

    private var first: String { member.displayName.split(separator: " ").first.map(String.init) ?? member.displayName }

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: Spacing.s) {
                Text(joined ? "Signing in" : "\(first) has not joined yet").font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                if let invitedAt, invitation == nil { Text("Last invited " + Format.day.string(from: invitedAt) + ".").font(Theme.font(12)).foregroundStyle(Theme.ink3) }
                if let inv = invitation, let url = inv.consoleURL {
                    Text((inv.emailed ? "Emailed to \(first), and here is the link too. " : "Send \(first) this link in a message. ") + "It works once, lasts a week, and a new one replaces it.")
                        .font(Theme.font(13)).foregroundStyle(Theme.ink2)
                    Text(url.absoluteString).font(.system(.caption, design: .monospaced)).foregroundStyle(Theme.ink).lineLimit(2).truncationMode(.middle).textSelection(.enabled)
                    HStack(spacing: Spacing.l) {
                        Button { UIPasteboard.general.string = url.absoluteString; copied = true } label: { Label(copied ? "Copied" : "Copy", systemImage: copied ? "checkmark" : "doc.on.doc") }
                        ShareLink(item: url, subject: Text("Your FamilyOS sign-in"), message: Text("Your way into our FamilyOS household. It works once and lasts a week.")) { Label("Send", systemImage: "square.and.arrow.up") }
                    }
                    .font(Theme.font(14, .medium)).foregroundStyle(Theme.primary)
                }
                if let error { Text(error).font(Theme.font(12)).foregroundStyle(Theme.danger) }
                Button { Task { await invite() } } label: {
                    HStack(spacing: Spacing.s) {
                        if busy { ProgressView().controlSize(.small) }
                        Text(joined || invitation != nil ? "New sign-in link" : "Invite").font(Theme.font(14, .semibold))
                    }
                }
                .glassButton(prominent: !joined && invitation == nil).tint(Theme.primary).disabled(busy)
            }
        }
        .sensoryFeedback(.success, trigger: copied)
    }

    private func invite() async {
        busy = true; defer { busy = false }
        do { invitation = try await API.shared.invite(member.id); copied = false; error = nil }
        catch { self.error = error.localizedDescription }
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

#Preview("A guardian looking at an adult") {
    NavigationStack { PersonView(member: PreviewData.members[1]) }.environmentObject(FamilyKeySample.session())
}
#Preview("Invite card") {
    InviteCard(member: PreviewData.members[1], joined: false, invitedAt: Date()).padding().paper()
}
