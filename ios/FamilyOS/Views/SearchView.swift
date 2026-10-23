import SwiftUI

/// The finder: pages, people, notices, plans and documents by a few letters.
struct SearchView: View {
    @EnvironmentObject var session: Session
    @State private var query = ""
    @State private var notices: [InboxRow] = []
    @State private var plans: [Plan] = []
    @State private var docs: [Document] = []
    @State private var open: Hit?

    enum Hit: Hashable, Identifiable {
        case notice(InboxRow), plan(Plan), document(Document), person(Member)
        var id: String {
            switch self {
            case .notice(let n): return "n" + n.id.uuidString; case .plan(let p): return "p" + p.id.uuidString
            case .document(let d): return "d" + d.id.uuidString; case .person(let m): return "m" + m.id.uuidString
            }
        }
    }

    private func has(_ s: String?) -> Bool { s?.localizedCaseInsensitiveContains(query) ?? false }

    var hits: [(String, [Hit])] {
        guard query.count >= 2 else { return [] }
        let people = session.members.filter { has($0.displayName) }.map(Hit.person)
        let ns = notices.filter { has($0.headline) || has($0.fromLabel) || has($0.preview.joined(separator: " ")) }.prefix(12).map(Hit.notice)
        let ps = plans.filter { has($0.title) || has($0.brief) }.map(Hit.plan)
        let ds = docs.filter { has($0.title) || has($0.holderName) || has($0.label) }.map(Hit.document)
        return [("People", people), ("Notices", Array(ns)), ("Plans", ps), ("Documents", ds)].filter { !$0.1.isEmpty }
    }

    var body: some View {
        Group {
            List {
                if query.count < 2 { Text("A name, a sender, a word from a notice, a plan, a document.").foregroundStyle(.secondary) }
                else if hits.isEmpty { Text("Nothing matches.").foregroundStyle(.secondary) }
                ForEach(hits, id: \.0) { group, items in
                    Section(group) {
                        ForEach(items) { h in NavigationLink(value: h) { HitRow(h: h) } }
                    }
                }
            }
            .scrollContentBackground(.hidden).paper()
            .navigationTitle("Search")
            .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .always), prompt: "Find anything")
            .navigationDestination(for: Hit.self) { h in
                switch h {
                case .notice(let n): NoticeView(artifactId: n.id, title: n.title)
                case .document(let d): NoticeView(artifactId: d.artifactId, title: d.title)
                case .plan(let p): PlanBrief(plan: p)
                case .person(let m): PersonView(member: m)
                }
            }
            .task {
                notices = (try? await API.shared.inbox(days: 365, limit: 300)) ?? []
                plans = (try? await API.shared.plans()) ?? []
                docs = (try? await API.shared.documents())?.documents ?? []
            }
        }
    }
}

struct HitRow: View {
    let h: SearchView.Hit
    var body: some View {
        switch h {
        case .notice(let n): Label(n.title, systemImage: "tray")
        case .plan(let p): Label(p.title, systemImage: "calendar")
        case .document(let d): Label("\(d.title) · \(d.label)", systemImage: "doc.text")
        case .person(let m): Label(m.displayName, systemImage: "person")
        }
    }
}

struct PlanBrief: View {
    let plan: Plan
    var body: some View {
        List {
            Section { Text(plan.brief) }
            if let s = plan.summary { Section("Summary") { Text(s) } }
            Section { Text("Itinerary, options and to-dos are on the console.").font(.footnote).foregroundStyle(.secondary) }
        }.navigationTitle(plan.title)
    }
}
