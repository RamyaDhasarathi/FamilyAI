import SwiftUI

/// Needs you: only what waits on a person. Each card says what happened, who it affects, by when, the words it came from,
/// what FamilyOS suggests and why, what waiting costs, and the buttons, which call the endpoints the server described.
/// A button that is a link goes where it says when the app has that place (a notice, the map, an errand) and is left out when it does not.
struct DecisionsView: View {
    @State private var cards: [DecisionCard] = []
    @State private var loaded = false
    @State private var busy: String?
    @State private var said: String?
    @State private var skipped = 0
    private let isSample: Bool
    private static let day: DateFormatter = { let f = DateFormatter(); f.dateFormat = "d MMM"; return f }()

    init() { isSample = false }

    /// Cards in hand, for previews: nothing is fetched or sent.
    init(sample: [DecisionCard]) {
        _cards = State(initialValue: sample)
        _loaded = State(initialValue: true)
        isSample = true
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.m) {
                Text("Needs you").font(Theme.font(28, .bold)).foregroundStyle(Theme.ink)
                Text(!loaded ? "Loading" : cards.isEmpty ? "Nothing is waiting on you" : "\(cards.count) \(cards.count == 1 ? "decision" : "decisions") waiting")
                    .font(Theme.font(14)).foregroundStyle(Theme.ink3)
                if let said { Text(said).font(Theme.font(13)).foregroundStyle(Theme.warning) }
                ForEach(cards) { card in cardView(card) }
                if skipped > 0 {
                    Text("\(skipped) more \(skipped == 1 ? "is" : "are") waiting that this version of the app cannot show; the console has \(skipped == 1 ? "it" : "them").")
                        .font(Theme.font(12)).foregroundStyle(Theme.ink3)
                }
            }
            .padding(Spacing.gutter)
        }
        .paper()
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        guard !isSample else { return }
        do { (cards, skipped) = try await API.shared.decisionsLossy(); said = nil } catch { said = "Could not load: \(error.localizedDescription)" }
        loaded = true
    }

    private func run(_ action: DecisionAction, card: DecisionCard) async {
        guard !isSample else { return }
        busy = card.id
        defer { busy = nil }
        do { try await API.shared.perform(action); await load() } catch { said = error.localizedDescription }
    }

    @ViewBuilder private func cardView(_ c: DecisionCard) -> some View {
        Card {
            VStack(alignment: .leading, spacing: Spacing.s) {
                HStack(spacing: Spacing.s) {
                    Tag(text: tag(c.kind), symbol: symbol(c.kind), tint: tint(c))
                    if let d = c.deadline { Text((c.late ? "was " : "by ") + Self.day.string(from: d)).font(Theme.font(12)).foregroundStyle(Theme.ink3) }
                    if !c.affects.isEmpty { Text("· " + c.affects.joined(separator: ", ")).font(Theme.font(12)).foregroundStyle(Theme.ink3).lineLimit(1) }
                }
                Text(c.title).font(Theme.font(17, .semibold)).foregroundStyle(Theme.ink)
                Text(c.happened).font(Theme.font(13)).foregroundStyle(Theme.ink2)
                if let q = c.source.quote, !q.isEmpty {
                    Text("“\(q)”").font(Theme.font(12)).foregroundStyle(Theme.ink2).padding(Spacing.s).frame(maxWidth: .infinity, alignment: .leading)
                        .background(Theme.line.opacity(0.5)).clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
                (Text("FamilyOS suggests ").font(Theme.font(13, .semibold)).foregroundStyle(Theme.primary) + Text(c.recommendation.text).font(Theme.font(13)).foregroundStyle(Theme.ink))
                    .padding(Spacing.s).frame(maxWidth: .infinity, alignment: .leading).background(Theme.primaryTint).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                // A heads-up costs nothing to leave; its sentence says so without the "if you wait".
                Text((c.kind == "heads_up" ? "" : "If you wait: ") + c.consequence).font(Theme.font(12)).foregroundStyle(Theme.ink3)
                if c.actions.contains(where: { $0.href == nil }) {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: Spacing.s) { buttons(c) }
                        VStack(alignment: .leading, spacing: Spacing.s) { buttons(c) }
                    }
                }
                links(c)
            }
        }
        .opacity(busy == c.id ? 0.5 : 1)
        .disabled(busy != nil)
    }

    @ViewBuilder private func buttons(_ c: DecisionCard) -> some View {
        ForEach(c.actions.filter { $0.href == nil }) { a in
            if let choices = a.choices {
                Menu {
                    ForEach(choices) { ch in Button(ch.label) { Task { await run(ch, card: c) } } }
                } label: { Text(a.label).font(Theme.font(14, .medium)).padding(.horizontal, 14).frame(minHeight: 40).background(Theme.card).overlay(Capsule().stroke(Theme.line)).clipShape(Capsule()) }
            } else if a.primary == true {
                Button { Task { await run(a, card: c) } } label: { Text(a.label).font(Theme.font(14, .semibold)).foregroundStyle(.white).padding(.horizontal, 16).frame(minHeight: 40).background(Theme.primary).clipShape(Capsule()) }
            } else {
                Button { Task { await run(a, card: c) } } label: { Text(a.label).font(Theme.font(14, .medium)).foregroundStyle(Theme.ink).padding(.horizontal, 14).frame(minHeight: 40).background(Theme.card).overlay(Capsule().stroke(Theme.line)).clipShape(Capsule()) }
            }
        }
    }

    /// The card's links that go somewhere in the app, and the notice it came from when no link already opens it.
    /// A destination built here, not a value pushed, so it is the same whichever stack the card is in.
    @ViewBuilder private func links(_ c: DecisionCard) -> some View {
        let places = c.actions.compactMap { a in a.href.flatMap(DecisionLink.init(href:)).map { (action: a, place: $0) } }
        let opensNotice = places.contains { if case .notice = $0.place { return true } else { return false } }
        ForEach(places, id: \.action.id) { p in
            NavigationLink { destination(p.place, title: c.title) } label: { linkLabel(p.action.label) }
        }
        if let id = c.source.artifactId, !opensNotice {
            NavigationLink { NoticeView(artifactId: id, title: c.title) } label: { linkLabel("Open the notice") }
        }
    }

    private func linkLabel(_ text: String) -> some View {
        HStack(spacing: 4) {
            Text(text).font(Theme.font(14, .medium))
            Image(systemName: "chevron.right").font(Theme.font(11, .semibold)).accessibilityHidden(true)
        }
        .foregroundStyle(Theme.primary).frame(minHeight: 32).contentShape(Rectangle())
    }

    @ViewBuilder private func destination(_ place: DecisionLink, title: String) -> some View {
        switch place {
        case .notice(let id): NoticeView(artifactId: id, title: title)
        case .map(let ref): FamilyMapView(ref: ref)
        case .errand(let id): ErrandView(errandId: id)
        }
    }

    private func tag(_ kind: String) -> String {
        ["date": "a date", "handed": "handed to you", "revision": "a change", "errand": "an errand", "purchase": "a purchase", "kid_request": "a question", "agent_proposal": "from your assistant", "pointer": "waiting in the app", "warranty": "a warranty", "document": "a document", "heads_up": "a heads-up"][kind] ?? kind.replacingOccurrences(of: "_", with: " ")
    }

    private func symbol(_ kind: String) -> String {
        ["date": "calendar", "handed": "hand.raised", "revision": "arrow.triangle.2.circlepath", "errand": "figure.walk", "purchase": "cart",
         "kid_request": "questionmark.bubble", "agent_proposal": "sparkles", "pointer": "app.badge", "warranty": "checkmark.shield",
         "document": "doc.text", "heads_up": "lightbulb"][kind] ?? "bell"
    }

    private func tint(_ c: DecisionCard) -> Color {
        if c.late { return Theme.danger }
        switch c.kind {
        case "heads_up": return Theme.primary
        case "warranty": return MapKind.warranty.color
        case "document": return MapKind.document.color
        case "pointer": return Space.school.color
        case "purchase", "errand": return Space.money.color
        default: return Theme.ink3
        }
    }
}

/// Where a decision card's link goes in the app. The console's addresses: `#/notices/<id>`, `#/map/<ref>`, `#/errands/<id>`.
/// Anything else (a space, the household page) has no screen of its own here, so it is not offered.
enum DecisionLink: Hashable {
    case notice(UUID), map(String), errand(UUID)

    init?(href: String) {
        guard href.hasPrefix("#/") else { return nil }
        let parts = href.dropFirst(2).split(separator: "/", maxSplits: 1).map(String.init)
        guard parts.count == 2 else { return nil }
        switch parts[0] {
        case "notices": guard let id = UUID(uuidString: parts[1]) else { return nil }; self = .notice(id)
        case "errands": guard let id = UUID(uuidString: parts[1]) else { return nil }; self = .errand(id)
        case "map": guard let ref = parts[1].removingPercentEncoding, ref.contains(":") else { return nil }; self = .map(ref)
        default: return nil
        }
    }
}

/// On the Family tab: how many decisions wait, and the way in.
struct DecisionsLinkCard: View {
    @State private var count: Int?
    var body: some View {
        NavigationLink { DecisionsView() } label: {
            Card {
                HStack(spacing: Spacing.m) {
                    Glyph(symbol: "bell.badge", tint: Theme.primary, size: 36)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Needs you").font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                        Text(count.map { $0 == 0 ? "Nothing is waiting" : "\($0) waiting, each with what to do" } ?? "Dates, hand-offs and approvals").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                    }
                    Spacer()
                    Image(systemName: "chevron.right").font(Theme.font(12, .semibold)).foregroundStyle(Theme.ink3).accessibilityHidden(true)
                }
            }
        }.buttonStyle(.plain)
        .task { count = (try? await API.shared.decisionsLossy())?.cards.count }
    }
}

// MARK: previews

extension PreviewData {
    static let decisionCards: [DecisionCard] = decode("""
    [
      {"id":"date:bbbbbbbb-0000-0000-0000-000000000001","kind":"date","title":"Science fair entries","happened":"Entry form and a one-page abstract","affects":["Noah"],"deadline":"\(day(4))","late":false,
       "source":{"artifact_id":"aaaaaaaa-0000-0000-0000-000000000003","quote":"Entries must reach the class teacher by Thursday"},
       "recommendation":{"text":"Accept it for Noah: it names a date and asks something of the family.","action":"accept"},
       "consequence":"Nothing is put on the calendar and no reminder is set until you answer.",
       "actions":[{"key":"accept","label":"Accept","method":"POST","path":"/v1/obligations/bbbbbbbb-0000-0000-0000-000000000001/decision","body_json":"{\\"status\\": \\"accepted\\"}","primary":true},
                  {"key":"dismiss","label":"Not this","method":"POST","path":"/v1/obligations/bbbbbbbb-0000-0000-0000-000000000001/decision","body_json":"{\\"status\\": \\"dismissed\\"}","primary":false},
                  {"key":"delegate","label":"Hand to…","primary":false,"choices":[{"key":"delegate","label":"Alex","method":"POST","path":"/v1/artifacts/aaaaaaaa-0000-0000-0000-000000000003/assign","body_json":"{}","primary":false}]},
                  {"key":"open","label":"Open the notice","href":"#/notices/aaaaaaaa-0000-0000-0000-000000000003","primary":false}]},
      {"id":"document:eeeeeeee-0000-0000-0000-000000000002","kind":"document","title":"Lily’s Passport runs out on 12 Mar 2027","happened":"It expires on 12 Mar 2027, in 149 days.","affects":["Lily"],"deadline":"2027-03-12","late":false,
       "source":{"artifact_id":"aaaaaaaa-0000-0000-0000-000000000006","quote":null},
       "recommendation":{"text":"Renew it with the office that issued it. When you share the renewed card or PDF, this clears by itself.","action":"accept"},
       "consequence":"Letting it lapse means an expired Passport can mean a fine, a refused claim or a refused booking.",
       "actions":[{"key":"todo","label":"Add a to-do to renew it","method":"POST","path":"/v1/todos","body_json":"{}","primary":true},
                  {"key":"renewed","label":"I have renewed it","method":"POST","path":"/v1/suggestions/doc%3A1/dismiss","body_json":"{}","primary":false},
                  {"key":"open","label":"See the document","href":"#/notices/aaaaaaaa-0000-0000-0000-000000000006","primary":false}]},
      {"id":"warranty:aaaaaaaa-0000-0000-0000-000000000009","kind":"warranty","title":"Track the warranty on Samsung refrigerator","happened":"The invoice from Croma says 12 months of warranty and 7 days to return it.","affects":[],"deadline":null,"late":false,
       "source":{"artifact_id":"aaaaaaaa-0000-0000-0000-000000000009","quote":"1 year manufacturer warranty"},
       "recommendation":{"text":"Track it, so you are told before the cover ends.","action":"accept"},
       "consequence":"Without an entry nothing warns you, and a claim missed by a day is lost.",
       "actions":[{"key":"track","label":"Track it","method":"POST","path":"/v1/finance/warranties","body_json":"{}","primary":true},
                  {"key":"dismiss","label":"Not this","method":"POST","path":"/v1/suggestions/warranty%3A1/dismiss","body_json":"{}","primary":false},
                  {"key":"open","label":"Read the invoice","href":"#/notices/aaaaaaaa-0000-0000-0000-000000000009","primary":false}]},
      {"id":"heads_up:busy:person:\(noah):41","kind":"heads_up","title":"Noah has 4 things in the next 7 days","happened":"PTM (Thu 16 Oct); Science fair (Fri 17 Oct); Swimming (Sat 18 Oct)","affects":[],"deadline":null,"late":false,
       "source":{"artifact_id":null,"quote":null},
       "recommendation":{"text":"Nobody asked; it shows in how your record connects. Open the map to see what it touches.","action":"open"},
       "consequence":"Nothing is wrong yet. This is a nudge, and it goes away when you say you have seen it.",
       "actions":[{"key":"open","label":"See how it connects","href":"#/map/person%3A\(noah)","primary":false},
                  {"key":"seen","label":"Got it","method":"POST","path":"/v1/suggestions/insight%3Abusy/dismiss","body_json":"{}","primary":false}]},
      {"id":"pointer:aaaaaaaa-0000-0000-0000-000000000010","kind":"pointer","title":"MyClassBoard has something new","happened":"The notification only said “New announcement”. What it says is inside the app.","affects":[],"deadline":null,"late":false,
       "source":{"artifact_id":"aaaaaaaa-0000-0000-0000-000000000010","quote":"New announcement"},
       "recommendation":{"text":"Have the phone read the app, with the phone next to the Mac, or share a screenshot of the announcement from the app.","action":"open"},
       "consequence":"Until it is read, any date or form in it is not on your list.",
       "actions":[{"key":"read:myclassboard","label":"Read it from the app","method":"POST","path":"/v1/errands","body_json":"{}","primary":true},
                  {"key":"handled","label":"I have seen it","method":"POST","path":"/v1/artifacts/aaaaaaaa-0000-0000-0000-000000000010/handled","body_json":"{}","primary":false},
                  {"key":"open","label":"Health","href":"#/space/health","primary":false}]}
    ]
    """)
}

#Preview("Needs you") {
    NavigationStack { DecisionsView(sample: PreviewData.decisionCards) }.environmentObject(PreviewData.session())
}

#Preview("Needs you · dark, large text") {
    NavigationStack { DecisionsView(sample: PreviewData.decisionCards) }
        .environmentObject(PreviewData.session()).preferredColorScheme(.dark).dynamicTypeSize(.xxxLarge)
}
