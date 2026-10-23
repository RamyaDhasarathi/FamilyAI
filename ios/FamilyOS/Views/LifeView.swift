import SwiftUI

/// Family: the people first, each a way to their own page, then the
/// household's life as spaces: what each counts, the bills coming up,
/// what FamilyOS is doing, the plans. One tab, since the family and its
/// life are one thing.
struct LifeView: View {
    @EnvironmentObject var session: Session
    @State private var notices: [InboxRow] = []
    @State private var plans: [Plan] = []
    @State private var money: Money?
    @State private var brief: Brief?
    @State private var errands: [Errand] = []
    @State private var todos: [Todo] = []
    @State private var offers: [Offer] = []
    @State private var path = NavigationPath()
    struct AskPrefill: Hashable { let text: String }

    /// Responsibilities, counted: the notices handed to them, the to-dos that are theirs.
    private func handling(_ m: Member) -> String? {
        let handed = notices.filter { $0.assignedTo == m.id && $0.handledAt == nil }.count
        let open = todos.filter { $0.assignedTo == m.id && $0.doneAt == nil }.count
        if handed == 0 && open == 0 { return nil }
        return [handed > 0 ? "\(handed) notice\(handed == 1 ? "" : "s")" : nil, open > 0 ? "\(open) to-do\(open == 1 ? "" : "s")" : nil].compactMap { $0 }.joined(separator: " · ")
    }

    private func accept(_ o: Offer) async {
        guard let out = try? await API.shared.acceptOffer(o.key) else { return }
        offers.removeAll { $0.key == o.key }
        if let q = out.ask { path.append(AskPrefill(text: q)) }
    }
    private func dismiss(_ o: Offer) async {
        try? await API.shared.dismissOffer(o.key)
        offers.removeAll { $0.key == o.key }
    }

    private var childIds: Set<UUID> { Set(session.members.filter(\.isChild).map(\.id)) }
    private var open: [InboxRow] { notices.filter { $0.state == "todo" } }
    private func openIn(_ sp: Space) -> Int { open.filter { Space.of($0, childIds: childIds) == sp }.count }
    private var bills: [BriefItem] { (brief?.items ?? []).filter { $0.action == "pay" && $0.reason != "handled" } }

    func count(_ sp: Space) -> String {
        switch sp {
        case .home: return "\(openIn(.home)) things pending"
        case .school: return "\(openIn(.school)) upcoming"
        case .health: return "\(openIn(.health)) to see"
        case .travel:
            if let t = plans.first(where: { $0.shape == "trip" && $0.status != "dropped" }) { return t.startsOn.map { Format.day.string(from: $0) } ?? t.title }
            return "No trip planned"
        case .money: return "\(money?.recurring.count ?? 0) bills"
        case .invest: return "\(openIn(.invest)) to decide"
        }
    }

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    ScreenHeader(title: "Family", subtitle: "\(session.members.count) people · spaces, money, errands and plans") { HeaderButton(symbol: "magnifyingglass", label: "Search", value: "search") }
                    OfflineBanner()
                    if !session.members.isEmpty {
                        PeopleRow(members: session.members)
                        let busy = session.members.compactMap { m in handling(m).map { (m, $0) } }
                        if !busy.isEmpty {
                            ListCard {
                                ForEach(busy, id: \.0.id) { m, line in
                                    NavigationLink(value: m) {
                                        HStack(spacing: Spacing.m) {
                                            Avatar(member: m, size: 32)
                                            Text(m.displayName.split(separator: " ").first.map(String.init) ?? m.displayName).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                                            Spacer()
                                            Text("handling " + line).font(Theme.font(13)).foregroundStyle(Theme.ink3)
                                            Image(systemName: "chevron.right").font(Theme.font(12, .semibold)).foregroundStyle(Theme.ink3).accessibilityHidden(true)
                                        }.padding(.horizontal, Spacing.s).padding(.vertical, 8)
                                    }.buttonStyle(.plain)
                                    .accessibilityLabel("\(m.displayName), handling \(line)")
                                    if m.id != busy.last?.0.id { RowDivider(inset: 48) }
                                }
                            }
                        }
                    }
                    if !offers.isEmpty {
                        Heading(title: "Offers")
                        Card(padding: 6) {
                            VStack(spacing: 0) {
                                ForEach(offers) { o in
                                    VStack(alignment: .leading, spacing: 6) {
                                        Text(o.title).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                                        Text(o.body).font(Theme.font(13)).foregroundStyle(Theme.ink2)
                                        Text(o.limit).font(Theme.font(12)).italic().foregroundStyle(Theme.ink3)
                                        HStack(spacing: Spacing.s) {
                                            if o.fyi {
                                                Button("Noted") { Task { await dismiss(o) } }.buttonStyle(.bordered).controlSize(.small)
                                            } else {
                                                Button(o.acceptLabel ?? "Yes") { Task { await accept(o) } }.buttonStyle(.borderedProminent).tint(Theme.primary).controlSize(.small)
                                                Button("Not now") { Task { await dismiss(o) } }.buttonStyle(.bordered).controlSize(.small)
                                            }
                                            Spacer()
                                        }.padding(.top, 2)
                                    }.padding(10)
                                    .accessibilityElement(children: .combine)
                                    if o.id != offers.last?.id { RowDivider() }
                                }
                            }
                        }
                    }
                    LazyVGrid(columns: [GridItem(.flexible(), spacing: 10), GridItem(.flexible(), spacing: 10)], spacing: 10) {
                        ForEach(Space.allCases) { sp in NavigationLink(value: sp) { SpaceTile(space: sp, count: count(sp)) }.buttonStyle(.plain) }
                    }
                    let week = (brief?.items ?? []).filter { $0.dueDate.map { $0 >= Calendar.current.startOfDay(for: Date()) } ?? false }.prefix(8)
                    HStack { Heading(title: "This week"); NavigationLink(value: "today") { Text("everything waiting").font(.subheadline).foregroundStyle(Theme.primary) } }
                    if week.isEmpty { Card { Text("Nothing dated this week.").foregroundStyle(Theme.ink3) } }
                    else { Card(padding: 6) { VStack(spacing: 0) { ForEach(Array(week)) { i in NavigationLink(value: i) { BriefLine(item: i) }.buttonStyle(.plain); if i.id != week.last?.id { Divider().padding(.leading, 56) } } } } }
                    Heading(title: "Upcoming bills")
                    if bills.isEmpty { Card { Text("No bill is waiting.").foregroundStyle(Theme.ink3) } }
                    else { Card(padding: 6) { VStack(spacing: 0) { ForEach(bills.prefix(8)) { i in NavigationLink(value: i) { BriefLine(item: i) }.buttonStyle(.plain); if i.id != bills.prefix(8).last?.id { Divider().padding(.leading, 56) } } } } }
                    Heading(title: "Being done for you")
                    let doing = errands.filter(\.isLive)
                    if doing.isEmpty { EmptyState(symbol: "cart", title: "Nothing right now", text: "Ask for a booking or a look and it appears here, written down in full before anything happens.") }
                    else { ListCard { ForEach(doing) { e in NavigationLink(value: e) { TaskRow(symbol: e.isPhoneApp ? "iphone" : "cart", tint: AgentState(errand: e.status).tint, title: e.title, detail: e.appLabel ?? e.service, trailing: .state(AgentState(errand: e.status))) }.buttonStyle(.plain); if e.id != doing.last?.id { RowDivider() } } } }
                    let home = notices.filter { Space.of($0, childIds: childIds) == .home }
                    Heading(title: "At home")
                    if home.isEmpty { Card { Text("Nothing at home yet.").foregroundStyle(Theme.ink3) } }
                    else { Card(padding: 6) { VStack(spacing: 0) { ForEach(home.prefix(12)) { r in NavigationLink(value: r) { InboxRowView(row: r, who: session.name(of: r.assignedTo)).padding(8) }.buttonStyle(.plain); if r.id != home.prefix(12).last?.id { Divider().padding(.leading, 48) } } } } }
                    if let m = money, !m.runningLow.isEmpty {
                        Heading(title: "Running low")
                        Card(padding: 6) {
                            VStack(spacing: 0) {
                                ForEach(m.runningLow.prefix(5)) { r in
                                    HStack(spacing: 10) {
                                        Glyph(symbol: "cart", tint: Space.home.color, size: 34)
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(r.item).foregroundStyle(Theme.ink)
                                            Text("\(r.merchant) · every \(r.everyDays) days · expected " + Format.day.string(from: r.expectedOn)).font(.caption).foregroundStyle(Theme.ink3)
                                        }
                                        Spacer()
                                        Text(r.status).font(.caption.weight(.medium)).foregroundStyle(r.status == "overdue" ? Theme.amber : Theme.ink3)
                                    }.padding(8)
                                }
                            }
                        }
                    }
                    EmptyState(symbol: "person.badge.plus", title: "Invite someone", text: "A new member is added from the console today, which mails them their own sign-in link. Inviting from the phone is next.")
                    BarSpace()
                }
                .padding(.horizontal, 16)
            }
            .paper()
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(for: Space.self) { sp in if sp == .money { MoneyView() } else { SpaceView(space: sp) } }
            .navigationDestination(for: AskPrefill.self) { q in AskView(prefill: q.text) }
            .navigationDestination(for: Member.self) { m in PersonView(member: m) }
            .navigationDestination(for: Errand.self) { e in ErrandView(errandId: e.id) }
            .navigationDestination(for: String.self) { key in if key == "today" { TodayView() } else if key == "settings" { SettingsView() } else { SearchView() } }
            .navigationDestination(for: InboxRow.self) { row in NoticeView(artifactId: row.id, title: row.title) }
            .navigationDestination(for: BriefItem.self) { i in
                if let id = i.artifactId { NoticeView(artifactId: id, title: i.title) } else { Card { Text(i.why) }.padding().paper() }
            }
            .navigationDestination(for: UUID.self) { id in NoticeView(artifactId: id, title: "Notice") }
            .refreshable { await load() }
            .task {
                await load()
                if let key = Debug.string("space"), let sp = Space(rawValue: key), path.isEmpty { path.append(sp) }
            }
        }
    }

    private func load() async {
        notices = (try? await API.shared.inbox(days: 30, limit: 200)) ?? []
        plans = (try? await API.shared.plans()) ?? []
        money = try? await API.shared.money()
        brief = try? await API.shared.brief()
        errands = (try? await API.shared.errands()) ?? []
        todos = (try? await API.shared.todos()) ?? []
        offers = (try? await API.shared.offers()) ?? []
        await session.refreshHousehold()
        #if canImport(ActivityKit)
        LiveActivities.sync(errands)
        #endif
    }
}

struct SpaceTile: View {
    let space: Space
    let count: String
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Glyph(symbol: space.symbol, tint: space.color, size: 38)
            VStack(alignment: .leading, spacing: 2) {
                Text(space.label).font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                Text(count).font(Theme.font(12)).foregroundStyle(Theme.ink3).lineLimit(1)
            }
        }
        .padding(14).frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.card).clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous).stroke(Theme.line, lineWidth: 0.5))
    }
}

/// The ledger of a space: spent here, charges again, around the house.
struct SpaceLedger: View {
    let space: Space
    let money: Money?
    var spent: [MoneyCharge] { (money?.charges ?? []).filter { space.categories.contains($0.category) } }
    var recurring: [MoneyRecurring] { (money?.recurring ?? []).filter { space.categories.contains($0.category) } }

    var body: some View {
        Heading(title: "Spent here")
        if spent.isEmpty { Card { Text("No receipts in this space yet.").foregroundStyle(Theme.ink3) } }
        else {
            Card(padding: 6) {
                VStack(spacing: 0) {
                    let inr = spent.filter { $0.currency == "INR" }.reduce(0) { $0 + $1.amount }
                    HStack(spacing: 10) {
                        Glyph(symbol: "banknote", tint: space.color, size: 36)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(Format.money(inr, "INR")).font(Theme.font(20, .semibold)).foregroundStyle(Theme.ink)
                            Text("in \(money?.days ?? 0) days · \(spent.count) charges").font(.caption).foregroundStyle(Theme.ink3)
                        }
                        Spacer()
                    }.padding(8)
                    Divider()
                    ForEach(spent.prefix(6)) { c in NavigationLink(value: c.artifactId) { LedgerLine(name: c.merchant, date: c.date, amount: c.amount, currency: c.currency).padding(8) }.buttonStyle(.plain) }
                }
            }
        }
        if !recurring.isEmpty {
            Heading(title: "Charges again")
            Card(padding: 6) { VStack(spacing: 0) { ForEach(recurring.prefix(6)) { r in NavigationLink(value: r.artifactId) { LedgerLine(name: r.merchant, date: r.nextDate, amount: r.nextAmount, currency: r.currency).padding(8) }.buttonStyle(.plain) } } }
        }
        if space == .home, let done = money?.services.lastDone, !done.isEmpty {
            Heading(title: "Around the house")
            Card { FlowChips(items: done.prefix(6).map { "\($0.kind) · " + Format.day.string(from: $0.date) }) }
        }
    }
}

struct FlowChips: View {
    let items: [String]
    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 120), spacing: 8, alignment: .leading)], alignment: .leading, spacing: 8) {
            ForEach(items, id: \.self) { Chip(text: $0) }
        }
    }
}

struct LedgerLine: View {
    let name: String; let date: Date; let amount: Double; let currency: String
    var body: some View {
        HStack {
            Text(name).foregroundStyle(Theme.ink).lineLimit(1)
            Spacer()
            Text(Format.day.string(from: date)).font(.caption).foregroundStyle(Theme.ink3)
            Text(Format.money(amount, currency)).font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink).monospacedDigit()
        }
    }
}

/// One space as its own small world.
struct SpaceView: View {
    @EnvironmentObject var session: Session
    let space: Space
    @State private var notices: [InboxRow] = []
    @State private var brief: Brief?
    @State private var money: Money?
    @State private var plans: [Plan] = []

    private var childIds: Set<UUID> { Set(session.members.filter(\.isChild).map(\.id)) }
    private var mine: [InboxRow] { notices.filter { Space.of($0, childIds: childIds) == space } }
    private var dated: [BriefItem] { let ids = Set(mine.map(\.id)); return (brief?.items ?? []).filter { ($0.artifactId.map(ids.contains) ?? false) && $0.dueDate != nil } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 12) {
                    Glyph(symbol: space.symbol, tint: space.color, size: 44)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(space.label).font(Theme.font(24, .medium, .serif)).foregroundStyle(Theme.ink)
                        Text("\(mine.count) notices · \(dated.count) dated").font(Theme.font(13)).foregroundStyle(Theme.ink3)
                    }
                }
                if !dated.isEmpty {
                    Heading(title: "Coming up")
                    Card(padding: 6) { VStack(spacing: 0) { ForEach(dated.prefix(8)) { i in NavigationLink(value: i) { BriefLine(item: i) }.buttonStyle(.plain) } } }
                }
                if space == .travel || space == .home {
                    Heading(title: space == .travel ? "Trips" : "Plans")
                    let live = plans.filter { $0.status != "dropped" && (($0.shape == "trip") == (space == .travel)) }
                    if live.isEmpty { Card { Text(space == .travel ? "No trip planned yet. Ask “plan our Dubai trip” and it appears here." : "No plan here yet. Ask “plan the week's meals” and it appears here.").font(Theme.font(13)).foregroundStyle(Theme.ink3) } }
                    ForEach(live) { p in
                        Card {
                            VStack(alignment: .leading, spacing: 4) {
                                HStack { Text(p.title).font(Theme.font(16, .semibold)).foregroundStyle(Theme.ink); Spacer(); Tag(text: p.status, tint: Space.travel.color) }
                                if let s = p.startsOn { Text(Format.day.string(from: s) + (p.endsOn.map { " to " + Format.day.string(from: $0) } ?? "")).font(.caption).foregroundStyle(Theme.ink3) }
                                if let s = p.summary { Text(s).font(Theme.font(13)).foregroundStyle(Theme.ink2).lineLimit(3) }
                            }
                        }
                    }
                }
                Heading(title: "What arrived")
                if mine.isEmpty { Card { Text("Nothing in this space yet.").foregroundStyle(Theme.ink3) } }
                else { Card(padding: 6) { VStack(spacing: 0) { ForEach(mine.prefix(30)) { r in NavigationLink(value: r) { InboxRowView(row: r, who: session.name(of: r.assignedTo)).padding(8) }.buttonStyle(.plain); if r.id != mine.prefix(30).last?.id { Divider().padding(.leading, 48) } } } } }
                SpaceLedger(space: space, money: money)
                if space == .school {
                    Heading(title: "The children")
                    Card(padding: 6) { VStack(spacing: 0) { ForEach(session.members.filter(\.isChild)) { m in NavigationLink(value: m) { HStack(spacing: 10) { Avatar(member: m, size: 36); VStack(alignment: .leading) { Text(m.displayName).foregroundStyle(Theme.ink); Text((m.school ?? "no school set") + (m.classLabel.map { ", class \($0)" } ?? "")).font(.caption).foregroundStyle(Theme.ink3) }; Spacer() }.padding(8) }.buttonStyle(.plain) } } }
                }
                BarSpace()
            }.padding(16)
        }
        .paper()
        .navigationBarTitleDisplayMode(.inline)
        .navigationDestination(for: Member.self) { m in PersonView(member: m) }
        .task { await load() }
    }

    private func load() async {
        notices = (try? await API.shared.inbox(days: 90, limit: 300)) ?? []
        brief = try? await API.shared.brief()
        money = try? await API.shared.money()
        plans = space == .travel ? ((try? await API.shared.plans()) ?? []) : []
    }
}

/// Money as far as mail can see it.
struct MoneyView: View {
    @State private var money: Money?
    @State private var error: String?
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 12) {
                    Glyph(symbol: Space.money.symbol, tint: Space.money.color, size: 44)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Money").font(Theme.font(24, .medium, .serif)).foregroundStyle(Theme.ink)
                        if let m = money { Text("\(m.month.charges) charges in \(m.month.days) days").font(Theme.font(13)).foregroundStyle(Theme.ink3) }
                    }
                }
                ErrorLine(text: error)
                if let m = money {
                    if !m.month.byCategory.isEmpty {
                        Heading(title: "By category")
                        Card(padding: 6) { VStack(spacing: 0) { ForEach(m.month.byCategory, id: \.self) { t in
                            HStack(spacing: 10) {
                                Glyph(symbol: Space.of(category: t.category).symbol, tint: Space.of(category: t.category).color, size: 30)
                                Text(t.category ?? "other").foregroundStyle(Theme.ink)
                                Spacer()
                                if let prev = t.previous, prev > 0 { Image(systemName: t.total >= prev ? "arrow.up.right" : "arrow.down.right").font(.caption).foregroundStyle(Theme.ink3) }
                                Text(Format.money(t.total, t.currency)).font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink).monospacedDigit()
                            }.padding(8)
                        } } }
                    }
                    if !m.recurring.isEmpty {
                        Heading(title: "Charges again")
                        Card(padding: 6) { VStack(spacing: 0) { ForEach(m.recurring) { r in NavigationLink(value: r.artifactId) { VStack(alignment: .leading, spacing: 2) { LedgerLine(name: r.merchant, date: r.nextDate, amount: r.nextAmount, currency: r.currency); Text("\(r.cadence) · \(r.times) so far").font(.caption).foregroundStyle(Theme.ink3) }.padding(8) }.buttonStyle(.plain) } } }
                    }
                    Heading(title: "Every charge")
                    if m.charges.isEmpty { Card { Text("No receipts yet.").foregroundStyle(Theme.ink3) } }
                    else { Card(padding: 6) { VStack(spacing: 0) { ForEach(m.charges) { c in NavigationLink(value: c.artifactId) { VStack(alignment: .leading, spacing: 2) { LedgerLine(name: c.merchant, date: c.date, amount: c.amount, currency: c.currency); Text(c.headline + (c.upcoming ? " · due \(c.due.map { Format.day.string(from: $0) } ?? "")" : "") + (c.settlesDue.map { " · settles the bill due \(Format.day.string(from: $0))" } ?? "")).font(.caption).foregroundStyle(Theme.ink3).lineLimit(1) }.padding(8) }.buttonStyle(.plain); Divider() } } } }
                }
                BarSpace()
            }.padding(16)
        }
        .paper()
        .navigationBarTitleDisplayMode(.inline)
        .task { do { money = try await API.shared.money(); error = nil } catch { self.error = error.localizedDescription } }
    }
}
