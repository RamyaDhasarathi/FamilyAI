import SwiftUI

/// My day: the signed-in person's own page, from what is already theirs.
/// What needs them, ideas ranked by what they take (with live product
/// options when a guardian switched search on), how FamilyOS may reach
/// them, their routines, what it has counted about them, and their Health
/// line if they use it. Nothing here is bought or sent on its own.
struct MyDayView: View {
    @State private var day: MyDay?
    @State private var error: String?
    @State private var said: String?
    @State private var shopOn = false
    /// Product options per idea, fetched when asked and dropped when closed.
    @State private var options: [String: ShopResults] = [:]
    @State private var looking: Set<String> = []
    @State private var busy: Set<String> = []
    @State private var askForget = false
    private let preview: Bool

    init(preview: MyDay? = nil, shopOn: Bool = false) {
        _day = State(initialValue: preview)
        _shopOn = State(initialValue: shopOn)
        self.preview = preview != nil
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 12) {
                    Glyph(symbol: "sun.max", tint: Theme.primary, size: 44)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("My day").font(Theme.font(24, .medium, .serif)).foregroundStyle(Theme.ink)
                        if let d = day { Text(Format.long.string(from: d.date) + " · " + d.displayName).font(Theme.font(13)).foregroundStyle(Theme.ink3) }
                    }
                }
                .accessibilityElement(children: .combine).accessibilityAddTraits(.isHeader)
                if let error { ErrorState(text: error, retry: { Task { await load() } }) }
                if let said { Text(said).font(Theme.font(13)).foregroundStyle(Theme.success).accessibilityAddTraits(.updatesFrequently) }
                if let d = day {
                    needsYou(d)
                    ideas(d)
                    // Quiet hours, the morning message and the daily cap are in one place on the phone: the profile.
                    NavigationLink { ProfileView() } label: {
                        Card {
                            HStack(spacing: Spacing.m) {
                                Image(systemName: "moon.zzz").foregroundStyle(Theme.ink2).frame(width: 24).accessibilityHidden(true)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("How FamilyOS reaches me").font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                                    Text("Morning message, quiet hours and the daily cap are in your profile.").font(Theme.font(12)).foregroundStyle(Theme.ink3).multilineTextAlignment(.leading)
                                }
                                Spacer()
                                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.ink3).accessibilityHidden(true)
                            }
                        }
                    }
                    .buttonStyle(.plain).accessibilityElement(children: .combine).accessibilityHint("Opens your profile")
                    routines(d)
                    learned(d)
                    if d.health.available { health(d.health) }
                } else if error == nil {
                    LoadingRows(count: 4)
                }
                BarSpace()
            }
            .padding(16)
        }
        .paper()
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task { if !preview { await load() } }
        .confirmationDialog("Forget what it has counted?", isPresented: $askForget, titleVisibility: .visible) {
            Button("Forget these", role: .destructive) { Task { await forget() } }
        } message: { Text("Ideas go back to the default order.") }
    }

    // MARK: sections

    @ViewBuilder private func needsYou(_ d: MyDay) -> some View {
        Heading(title: "Needs you")
        if d.needs.isEmpty { Card { Text("Nothing needs you right now.").font(Theme.font(14)).foregroundStyle(Theme.ink3) } }
        else {
            ListCard {
                ForEach(d.needs) { n in
                    let detail = [n.when, n.why].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · ")
                    let symbol = n.isLate ? "exclamationmark.circle" : symbolFor(n)
                    let tint = n.isLate ? Theme.warning : Theme.primary
                    if let id = n.artifactId {
                        NavigationLink { NoticeView(artifactId: id, title: n.title) } label: { TaskRow(symbol: symbol, tint: tint, title: n.title, detail: detail) }.buttonStyle(.plain)
                    } else {
                        TaskRow(symbol: symbol, tint: tint, title: n.title, detail: detail, trailing: .none)
                    }
                    if n.id != d.needs.last?.id { RowDivider() }
                }
            }
            if d.more > 0 { Text("and \(d.more) more on Today").font(Theme.font(12)).foregroundStyle(Theme.ink3) }
        }
    }

    private func symbolFor(_ n: MyDayNeed) -> String {
        switch n.action {
        case "pay": return "indianrupeesign.circle"
        case "attend", "arrive": return "calendar"
        case "submit", "bring": return "doc.text"
        case "renew": return "arrow.triangle.2.circlepath"
        default: return n.reason == "birthday" ? "gift" : "bell"
        }
    }

    @ViewBuilder private func ideas(_ d: MyDay) -> some View {
        Heading(title: "Ideas for you")
        Text("Ordered by what you accept; a kind you keep waving away goes quiet.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
        if d.suggestions.isEmpty { Card { Text("No ideas right now.").font(Theme.font(14)).foregroundStyle(Theme.ink3) } }
        else {
            Card(padding: 6) {
                VStack(spacing: 0) {
                    ForEach(d.suggestions) { s in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(s.title).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                            if let why = s.why, !why.isEmpty { Text(why).font(Theme.font(13)).foregroundStyle(Theme.ink2) }
                            HStack(spacing: Spacing.s) {
                                Button("Add") { Task { await accept(s) } }.buttonStyle(.borderedProminent).tint(Theme.primary).controlSize(.small)
                                if shopOn && !d.isChild {
                                    Button(options[s.key] == nil ? "Find options" : "Hide options") { Task { await find(s) } }.buttonStyle(.bordered).controlSize(.small)
                                }
                                Button("Not this") { Task { await dismiss(s) } }.buttonStyle(.bordered).controlSize(.small)
                                Spacer()
                                if busy.contains(s.key) || looking.contains(s.key) { ProgressView().controlSize(.small) }
                            }
                            .disabled(busy.contains(s.key))
                            .padding(.top, 2)
                            if let r = options[s.key] { ShopOptions(results: r) }
                        }
                        .padding(10)
                        if s.id != d.suggestions.last?.id { RowDivider(inset: 10) }
                    }
                }
            }
        }
    }

    @ViewBuilder private func routines(_ d: MyDay) -> some View {
        Heading(title: "My autopilot")
        Text("Rules that run on a clock or when something happens. They only read and say. Add, pause or stop them in the console.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
        if d.routines.isEmpty { Card { Text("None yet.").font(Theme.font(14)).foregroundStyle(Theme.ink3) } }
        else {
            ListCard {
                ForEach(d.routines) { r in
                    TaskRow(symbol: "clock.arrow.circlepath", tint: Theme.primary, title: r.instruction, detail: r.when, trailing: .none)
                    if r.id != d.routines.last?.id { RowDivider() }
                }
            }
        }
    }

    @ViewBuilder private func learned(_ d: MyDay) -> some View {
        Heading(title: "What it has counted about me")
        Text("Only which kinds of ideas you add or wave away, over 90 days. It only orders and quiets ideas.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
        if d.learned.isEmpty { Card { Text("Nothing yet.").font(Theme.font(14)).foregroundStyle(Theme.ink3) } }
        else {
            ListCard {
                ForEach(d.learned) { k in
                    TaskRow(symbol: k.quiet ? "speaker.slash" : "chart.bar", tint: k.quiet ? Theme.ink3 : Theme.primary, title: k.kind,
                            detail: "added \(k.accepted) · waved away \(k.dismissed)" + (k.quiet ? " · now quiet" : ""), trailing: .none)
                    if k.id != d.learned.last?.id { RowDivider() }
                }
            }
            Button("Forget these") { askForget = true }.font(Theme.font(14, .semibold)).foregroundStyle(Theme.danger)
        }
    }

    @ViewBuilder private func health(_ h: MyHealth) -> some View {
        Heading(title: "My body")
        Card {
            Text(h.sync ? (h.line ?? "Nothing has arrived from the Health app yet.") : "Off. Switch on Health device data on the Family tab.")
                .font(Theme.font(14)).foregroundStyle(h.sync ? Theme.ink : Theme.ink3)
        }
    }

    // MARK: doing

    private func load() async {
        do {
            day = try await API.shared.myDay(); error = nil
            shopOn = (try? await API.shared.shopEnabled()) ?? false
        } catch { self.error = error.localizedDescription }
    }

    private func accept(_ s: MyDayIdea) async {
        busy.insert(s.key); defer { busy.remove(s.key) }
        do { try await API.shared.acceptSuggestion(s.key); said = "Added to to-dos."; options[s.key] = nil; await load() }
        catch { self.error = error.localizedDescription }
    }

    private func dismiss(_ s: MyDayIdea) async {
        busy.insert(s.key); defer { busy.remove(s.key) }
        do { try await API.shared.dismissSuggestion(s.key); said = nil; options[s.key] = nil; await load() }
        catch { self.error = error.localizedDescription }
    }

    /// Opens or closes the options under an idea. Nothing is kept once closed.
    private func find(_ s: MyDayIdea) async {
        if options[s.key] != nil { options[s.key] = nil; return }
        looking.insert(s.key); defer { looking.remove(s.key) }
        do { options[s.key] = try await API.shared.shopSearch(suggestion: s.key) }
        catch { self.error = error.localizedDescription }
    }

    private func forget() async {
        do { try await API.shared.forgetLearned(); said = "Forgotten."; await load() }
        catch { self.error = error.localizedDescription }
    }
}

/// Live product options under an idea: the seller, the price in its own
/// currency, the rating with its scale, whether it may not ship here, and
/// the seller's link exactly as the catalogue returned it.
struct ShopOptions: View {
    let results: ShopResults
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let e = results.error { Text(e).font(Theme.font(12)).foregroundStyle(Theme.warning) }
            ForEach(results.messages ?? [], id: \.self) { Text($0).font(Theme.font(12)).foregroundStyle(Theme.ink3) }
            if results.products.isEmpty && results.error == nil { Text("Nothing came back for this.").font(Theme.font(12)).foregroundStyle(Theme.ink3) }
            ForEach(results.products) { p in ProductRow(product: p) }
            Text([results.note, "Nothing is bought here."].compactMap { $0 }.joined(separator: " ")).font(Theme.font(11)).foregroundStyle(Theme.ink3)
        }
        .padding(10)
        .background(Theme.paper).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

struct ProductRow: View {
    let product: ShopProduct

    private var detail: String {
        var parts: [String] = []
        if let s = product.seller?.name { parts.append(s) }
        if let p = product.price { parts.append(Format.money(p.amount, p.currency)) }
        if let r = product.rating {
            let value = r.value == r.value.rounded() ? String(Int(r.value)) : String(format: "%.1f", r.value)
            let scale = r.scaleMax.map { $0 == $0.rounded() ? String(Int($0)) : String($0) }
            parts.append(value + (scale.map { " of \($0)" } ?? "") + (r.count.map { " (\($0) reviews)" } ?? ""))
        }
        if let o = product.options, !o.isEmpty { parts.append(o) }
        if product.local == false { parts.append("check it ships to you") }
        if product.available == false { parts.append("out of stock") }
        return parts.joined(separator: " · ")
    }

    var body: some View {
        // The link as returned, every query parameter kept; it opens in Safari.
        let row = HStack(alignment: .top, spacing: Spacing.m) {
            Group {
                if let s = product.imageUrl, let u = URL(string: s) {
                    AsyncImage(url: u) { img in img.resizable().scaledToFill() } placeholder: { Theme.line }
                } else {
                    Image(systemName: "bag").font(Theme.font(17)).foregroundStyle(Theme.ink3).frame(maxWidth: .infinity, maxHeight: .infinity).background(Theme.line)
                }
            }
            .frame(width: 44, height: 44).clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous)).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(product.title ?? "Untitled").font(Theme.font(14, .medium)).foregroundStyle(Theme.primary).multilineTextAlignment(.leading)
                if !detail.isEmpty { Text(detail).font(Theme.font(12)).foregroundStyle(Theme.ink3).multilineTextAlignment(.leading) }
            }
            Spacer(minLength: 0)
            Image(systemName: "arrow.up.right.square").font(Theme.font(13)).foregroundStyle(Theme.ink3).accessibilityHidden(true)
        }
        if let url = URL(string: product.url) {
            Link(destination: url) { row }.buttonStyle(.plain)
                .accessibilityElement(children: .combine).accessibilityHint("Opens the seller's page in Safari")
        } else {
            row.accessibilityElement(children: .combine)
        }
    }
}

/// How FamilyOS may reach me: the morning message, the quiet window, and
/// at most how many unprompted messages a day. Saved with one tap.
struct ReachCard: View {
    let saved: () -> Void
    @State private var morning: Int
    @State private var quietFrom: Int
    @State private var quietTo: Int
    @State private var cap: Int
    @State private var saving = false
    @State private var error: String?
    /// The morning picker's "off".
    private static let off = -1
    private static let caps = [0, 1, 2, 3, 4, 5, 8, 10, 15, 20]

    init(prefs: ReachPrefs, saved: @escaping () -> Void) {
        self.saved = saved
        _morning = State(initialValue: prefs.morningHour ?? Self.off)
        _quietFrom = State(initialValue: prefs.quietFrom ?? 21)
        _quietTo = State(initialValue: prefs.quietTo ?? 7)
        _cap = State(initialValue: prefs.dailyCap ?? 3)
    }

    static func hourName(_ h: Int) -> String { "\(h % 12 == 0 ? 12 : h % 12) \(h < 12 ? "am" : "pm")" }

    var body: some View {
        Heading(title: "How FamilyOS reaches me")
        Card(padding: 6) {
            VStack(spacing: 0) {
                row("Morning message") {
                    Picker("Morning message", selection: $morning) {
                        Text("Off").tag(Self.off)
                        ForEach(0..<24, id: \.self) { Text(Self.hourName($0)).tag($0) }
                    }
                }
                RowDivider(inset: 10)
                row("Quiet from") { Picker("Quiet from", selection: $quietFrom) { ForEach(0..<24, id: \.self) { Text(Self.hourName($0)).tag($0) } } }
                RowDivider(inset: 10)
                row("Quiet until") { Picker("Quiet until", selection: $quietTo) { ForEach(0..<24, id: \.self) { Text(Self.hourName($0)).tag($0) } } }
                RowDivider(inset: 10)
                row("At most a day") { Picker("At most a day", selection: $cap) { ForEach(Self.caps, id: \.self) { Text($0 == 0 ? "None" : "\($0)").tag($0) } } }
                HStack {
                    if let error { Text(error).font(Theme.font(12)).foregroundStyle(Theme.danger) }
                    Spacer()
                    if saving { ProgressView().controlSize(.small) }
                    Button("Save") { Task { await save() } }.buttonStyle(.borderedProminent).tint(Theme.primary).controlSize(.small).disabled(saving)
                }
                .padding(10)
            }
        }
    }

    private func row<P: View>(_ label: String, @ViewBuilder picker: () -> P) -> some View {
        HStack {
            Text(label).font(Theme.font(15)).foregroundStyle(Theme.ink)
            Spacer()
            picker().labelsHidden().pickerStyle(.menu).tint(Theme.primary)
        }
        .padding(.horizontal, 10).padding(.vertical, 4).frame(minHeight: 44)
    }

    private func save() async {
        saving = true; defer { saving = false }
        do {
            _ = try await API.shared.setReach(quietFrom: quietFrom, quietTo: quietTo, dailyCap: cap, morningHour: morning == Self.off ? nil : morning)
            error = nil; saved()
        } catch { self.error = error.localizedDescription }
    }
}

#if DEBUG
extension PreviewData {
    static let myDay: MyDay = decode("""
    {"date":"\(day(0))","display_name":"Alex","role":"guardian","more":3,"counts":{},
     "needs":[
       {"reason":"overdue","rank":1,"title":"Return the library book","why":"Was due on Monday","when":"2 days ago","artifact_id":"aaaaaaaa-0000-0000-0000-000000000011"},
       {"reason":"due","rank":2,"title":"Pay Term 2 tuition fee","why":"₹48,000 to Oakridge Global School","when":"today","due_date":"\(day(0))","action":"pay","artifact_id":"aaaaaaaa-0000-0000-0000-000000000002"},
       {"reason":"assigned","rank":3,"title":"Sign the field-trip form","why":"Kanimozhi handed this to you","when":"Thursday"}
     ],
     "suggestions":[
       {"key":"\(lily):2026-10-21:gift","title":"A gift for Lily's birthday","why":"Her birthday is on the 21st","due_date":"\(day(5))","link":null},
       {"key":"exam:science","title":"Revision notes for the science test","why":"The test is next Wednesday","due_date":"\(day(7))","link":null}
     ],
     "routines":[{"id":"eeeeeeee-0000-0000-0000-000000000001","instruction":"Tell me what is due this week","when":"Sundays at 6 pm"}],
     "reach_me":{"quiet_from":21,"quiet_to":7,"daily_cap":3,"morning_hour":7},
     "learned":[{"kind":"gift","accepted":4,"dismissed":0,"quiet":false},{"kind":"outing","accepted":0,"dismissed":5,"quiet":true}],
     "health":{"available":true,"sync":true,"line":"7,840 steps a day this week, 6 h 50 min of sleep"}}
    """)

    static let shopResults: ShopResults = decode("""
    {"query":"birthday gift","error":null,"messages":["Prices include tax where the seller says so."],
     "note":"Fetched just now and not kept. Prices and stock change; check the seller's page.",
     "products":[
       {"title":"Wooden puzzle set, 4 in 1","seller":{"name":"Kidzy Toys","domain":"kidzy.in"},"price":{"amount":1299,"currency":"INR"},"url":"https://kidzy.in/products/puzzle?variant=1&utm_source=shop","image_url":null,"rating":{"value":4.6,"scale_max":5,"count":212},"options":"Age: 4-6","available":true,"local":true},
       {"title":"Watercolour starter kit","seller":{"name":"Paper Owl","domain":"paperowl.com.au"},"price":{"amount":34.95,"currency":"AUD"},"url":"https://paperowl.com.au/products/kit?variant=9","image_url":null,"rating":null,"options":"","available":false,"local":false}
     ]}
    """)
}

#Preview("My day") { NavigationStack { MyDayView(preview: PreviewData.myDay, shopOn: true) } }
#Preview("My day · dark, options open") {
    NavigationStack { ScrollView { ShopOptions(results: PreviewData.shopResults).padding() }.paper() }.preferredColorScheme(.dark)
}
#endif
