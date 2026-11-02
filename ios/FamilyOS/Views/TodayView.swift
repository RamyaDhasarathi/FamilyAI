import SwiftUI

/// Today, read top to bottom like a morning note: the greeting and one
/// line that says what the day holds, the people, the next thing up, what
/// needs you, what FamilyOS is doing, then the day itself. What is late
/// stays on today until someone acts; the week ahead is on Family.
struct TodayView: View {
    @EnvironmentObject var session: Session
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var brief: Brief?
    @State private var events: [CalendarEvent] = []
    @State private var errands: [Errand] = []
    @State private var checks: [DocumentCheck] = []
    @State private var ideas: [Suggestion] = []
    @State private var low: [RunningLow] = []
    @State private var loaded = false
    @State private var error: String?
    @State private var decided = 0
    @State private var path = NavigationPath()
    @State private var showAdd = false

    private var today: [Entry] { Entry.merge(brief: brief, events: events, on: Date()) }
    private var entries: [Entry] { today }
    private var next: Entry? { Entry.next(in: today, day: Date()) }
    /// What still wants a decision and is not yet late. What is late is in `late`, and only there.
    private var waiting: [BriefItem] { (brief?.items ?? []).filter { ($0.status == "proposed" || $0.reason == "undecided" || $0.reason == "needs_you") && !isLate($0) } }
    private var live: [Errand] { errands.filter { let s = AgentState(errand: $0.status); return s.isLive || s == .needsYou || s == .waitingApproval || s == .failed } }
    /// A message that looks like a scam: said before anything else, never as a task.
    private var scams: [BriefItem] { (brief?.items ?? []).filter { $0.reason == "scam" } }
    private var noticed: BriefItem? { (brief?.items ?? []).first { !($0.clashes ?? []).isEmpty } }
    /// What is already late and still open: it belongs on today until someone acts.
    private var late: [BriefItem] { (brief?.items ?? []).filter(isLate) }
    private func isLate(_ i: BriefItem) -> Bool { (i.reason == "overdue" || i.reason == "missed") && i.status != "dismissed" }
    /// Everything a person must still decide, late or not: the number the first line says.
    private var undecided: Int { waiting.count + late.filter { $0.status == "proposed" }.count }
    private var firstName: String { (session.member?.displayName ?? brief?.displayName ?? "").split(separator: " ").first.map(String.init) ?? "" }

    /// One sentence for the day. What needs a person first; then the next thing; else quiet.
    private var summary: String {
        var parts: [String] = []
        if undecided > 0 { parts.append("\(undecided) thing\(undecided == 1 ? "" : "s") need\(undecided == 1 ? "s" : "") you") }
        if let n = next, let t = n.time, t != "any time" { parts.append("next at \(t)") }
        else if today.isEmpty && loaded { parts.append("nothing on the calendar") }
        if let e = live.first(where: { AgentState(errand: $0.status) == .needsYou }) { parts.append("an errand needs you: \(e.title)") }
        return parts.isEmpty ? Format.long.string(from: Date()) : parts.joined(separator: " · ").prefix(1).uppercased() + parts.joined(separator: " · ").dropFirst()
    }

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: Spacing.xl) {
                    // The first-run checklist sits under the greeting; hidden, it leaves no gap.
                    VStack(alignment: .leading, spacing: 0) {
                        header
                        SetupChecklistCard(spacingAbove: Spacing.xl)
                    }
                    OfflineBanner()
                    if let error, brief == nil { ErrorState(text: error) { Task { await load() } } }
                    if !loaded && error == nil { LoadingRows(count: 3) }
                    ForEach(scams) { i in ScamCard(item: i) }
                    if let n = next { NextUpCard(entry: n) }
                    if !late.isEmpty || !waiting.isEmpty { needsYouAll }
                    if !live.isEmpty { inProgress }
                    if !ideas.isEmpty { ideasSection }
                    if !low.isEmpty { lowSection }
                    runsCard
                    daySection
                    if let n = noticed { NoticedCard(item: n) }
                    ForEach(checks, id: \.self) { c in DocumentCheckCard(check: c) }
                    if !session.members.isEmpty { PeopleRow(members: session.members) }
                    Text("The week ahead is on Family.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                    if let error, brief != nil { ErrorLine(text: error) }
                    BarSpace()
                }
                .padding(.horizontal, Spacing.gutter)
            }
            .paper()
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(for: String.self) { key in
                switch key {
                case "inbox": InboxView()
                case "search": SearchView()
                default: SettingsView()
                }
            }
            .navigationDestination(for: Member.self) { m in PersonView(member: m) }
            .navigationDestination(for: Errand.self) { e in ErrandView(errandId: e.id) }
            .navigationDestination(for: UUID.self) { id in ErrandView(errandId: id) }
            .navigationDestination(for: Entry.self) { e in
                if let id = e.artifactId { NoticeView(artifactId: id, title: e.title) } else { EventView(entry: e) }
            }
            .navigationDestination(for: BriefItem.self) { i in
                if let id = i.artifactId { NoticeView(artifactId: id, title: i.title) } else { Card { Text(i.why) }.padding().paper() }
            }
            .sheet(isPresented: $showAdd, onDismiss: { Task { await load() } }) { AddNoticeView() }
            .sensoryFeedback(.success, trigger: decided)
            .refreshable { await load() }
            .task {
                await load()
                // A debug build opens an errand straight away: `-errand <id>`.
                if let id = Debug.string("errand").flatMap(UUID.init), path.isEmpty { path.append(id) }
            }
        }
    }

    // MARK: sections

    /// The greeting as a note's first line: the time of day small, the name
    /// large in serif, then one sentence about the day. Controls sit on the
    /// first line so the name never has to share its width with them.
    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .center) {
                Text(greeting()).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink3)
                Spacer()
                GlassGroup(spacing: 12) {
                    HStack(spacing: Spacing.s) {
                        Button { showAdd = true } label: {
                            Image(systemName: "plus").font(Theme.font(17, .semibold)).foregroundStyle(Theme.ink).frame(width: 44, height: 44).glassCircle()
                        }.buttonStyle(.plain).accessibilityLabel("Add a notice")
                        HeaderButton(symbol: "tray", label: "Inbox", value: "inbox")
                        HeaderButton(symbol: "magnifyingglass", label: "Search", value: "search")
                        ProfileButton()
                    }
                }
            }
            Text(firstName.isEmpty ? "Hello" : firstName).font(Theme.font(34, .regular, .serif)).foregroundStyle(Theme.ink).lineLimit(1).minimumScaleFactor(0.7)
            Text(summary).font(Theme.font(16)).foregroundStyle(Theme.ink2).lineLimit(2)
            chips
        }
        .padding(.top, Spacing.s)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isHeader)
        .accessibilityLabel("\(greeting()), \(firstName). \(summary)")
    }

    /// Weather and the next holiday as small pills under the greeting, one line each, side by side.
    @ViewBuilder private var chips: some View {
        let weather = brief?.context?.weather.flatMap { w -> String? in
            let today = w.components(separatedBy: ". Tomorrow").first ?? w
            return today.replacingOccurrences(of: "Today: ", with: "").trimmingCharacters(in: CharacterSet(charactersIn: ". "))
        }
        let holiday = brief?.context?.holidays?.first.map { "\($0.name) · \(Format.day.string(from: $0.date))" }
        if (weather ?? "").isEmpty == false || holiday != nil {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: Spacing.s) {
                    if let weather, !weather.isEmpty { Pill(symbol: "cloud.sun", text: weather) }
                    if let holiday { Pill(symbol: "sparkles", text: holiday) }
                }
            }
            .padding(.top, 4)
            .accessibilityElement(children: .combine)
        }
    }

    /// Everything a person has to decide, late ones first and marked, in one card.
    private var needsYouAll: some View {
        let rows = Array((late + waiting).prefix(8))
        return VStack(alignment: .leading, spacing: Spacing.s) {
            HStack(alignment: .firstTextBaseline) {
                SectionLabel(title: "Needs you")
                Text("\(late.count + waiting.count)").font(Theme.font(13, .semibold)).foregroundStyle(Theme.ink3)
            }
            ListCard {
                ForEach(rows) { i in
                    NavigationLink(value: i) {
                        if isLate(i) {
                            let when = ["Late", Format.when(i.dueDate, i.dueTime), i.subjectName].compactMap { $0 }.joined(separator: " · ")
                            TaskRow(symbol: "exclamationmark.circle.fill", tint: Theme.danger, title: i.title, detail: when)
                        } else { BriefLine(item: i) }
                    }.buttonStyle(.plain)
                    decision(for: i)
                    if i.id != rows.last?.id { RowDivider() }
                }
            }
            Text("Accepting puts a date on the calendar and tells whoever it is for. Nothing is paid or booked here.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
        }
    }

    /// The school run from home, in a card of its own so the greeting stays short;
    /// red when live traffic is markedly worse than usual.
    @ViewBuilder private var runsCard: some View {
        if let runs = brief?.context?.schoolRuns, !runs.isEmpty {
            VStack(alignment: .leading, spacing: Spacing.s) {
              SectionLabel(title: "Getting out")
              Card(padding: 14) {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(runs, id: \.self) { r in
                        HStack(alignment: .firstTextBaseline, spacing: Spacing.s) {
                            Image(systemName: "car").font(Theme.font(13)).foregroundStyle(Theme.ink3).frame(width: 18)
                            Text(r.line).font(Theme.font(14)).foregroundStyle((r.delayMinutes ?? 0) >= 8 ? Theme.danger : Theme.ink2)
                        }
                    }
                }
              }
            }
        }
    }

    /// To-dos an event implies: a birthday asks for a gift, a trip for passports. Never added on its own.
    private var ideasSection: some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            SectionLabel(title: "You may want to")
            ListCard {
                ForEach(ideas.prefix(4)) { i in
                    TaskRow(symbol: "lightbulb", tint: Theme.amber, title: i.title, detail: i.why, trailing: .none)
                    HStack(spacing: Spacing.s) {
                        Button("Add") { Task { await accept(i) } }.buttonStyle(.borderedProminent).tint(Theme.primary).controlSize(.small)
                        Button("Not now") { Task { await waveAway(i) } }.buttonStyle(.bordered).tint(Theme.ink2).controlSize(.small)
                        if let l = i.link, let url = URL(string: l) { Link("Look", destination: url).font(Theme.font(13, .medium)).padding(.leading, 4) }
                        Spacer()
                    }.padding(.leading, 54).padding(.bottom, Spacing.s)
                    if i.id != ideas.prefix(4).last?.id { RowDivider() }
                }
            }
        }
    }

    /// What the household buys on a rhythm and is about to run out of, with the shop's own search to reorder.
    private var lowSection: some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            SectionLabel(title: "Running low")
            ListCard {
                ForEach(low.prefix(4)) { r in
                    HStack {
                        TaskRow(symbol: "cart", tint: Space.home.color, title: r.item, detail: "\(r.merchant) · every \(r.everyDays) days" + (r.status == "overdue" ? " · due" : ""), trailing: .none)
                        if let l = r.reorderUrl, let url = URL(string: l) { Link("Reorder", destination: url).font(Theme.font(13, .semibold)).foregroundStyle(Theme.primary).padding(.trailing, Spacing.s) }
                    }
                    if r.id != low.prefix(4).last?.id { RowDivider() }
                }
            }
            Text("Reorder opens the shop's own search. Nothing is bought here.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
        }
    }

    private func accept(_ i: Suggestion) async {
        try? await API.shared.acceptSuggestion(i.key); ideas.removeAll { $0.key == i.key }; decided += 1
    }
    private func waveAway(_ i: Suggestion) async {
        try? await API.shared.dismissSuggestion(i.key); ideas.removeAll { $0.key == i.key }
    }

    private var needsYou: some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            SectionLabel(title: "Needs you")
            ListCard {
                ForEach(waiting.prefix(8)) { i in
                    NavigationLink(value: i) { BriefLine(item: i) }.buttonStyle(.plain)
                    decision(for: i)
                    if i.id != waiting.prefix(8).last?.id { RowDivider() }
                }
            }
            Text("Accepting puts a date on the calendar and tells whoever it is for. Nothing is paid or booked here.").font(Theme.font(12)).foregroundStyle(Theme.ink3).padding(.horizontal, Spacing.xs)
        }
    }

    private var inProgress: some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            SectionLabel(title: "FamilyOS is doing")
            ListCard {
                ForEach(live) { e in
                    NavigationLink(value: e) {
                        TaskRow(symbol: e.isPhoneApp ? "iphone" : "cart", tint: AgentState(errand: e.status).tint, title: e.title,
                                detail: e.error ?? e.appLabel ?? e.service, trailing: .state(AgentState(errand: e.status)))
                    }.buttonStyle(.plain)
                    if e.id != live.last?.id { RowDivider() }
                }
            }
        }
    }

    private var lateSection: some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            SectionLabel(title: "Late")
            ListCard {
                ForEach(late.prefix(6)) { i in
                    NavigationLink(value: i) { BriefLine(item: i) }.buttonStyle(.plain)
                    decision(for: i)
                    if i.id != late.prefix(6).last?.id { RowDivider() }
                }
            }
        }
    }

    /// Accept or dismiss, under a row that is still proposed; the same two
    /// buttons whether the item is late or coming up.
    @ViewBuilder private func decision(for i: BriefItem) -> some View {
        if let oid = i.obligationId, i.status == "proposed" {
            HStack(spacing: Spacing.s) {
                Button("Accept") { Task { await decide(oid, "accepted") } }.buttonStyle(.borderedProminent).tint(Theme.primary).controlSize(.small)
                    .accessibilityLabel("Accept \(i.title)")
                Button("Not this") { Task { await decide(oid, "dismissed") } }.buttonStyle(.bordered).tint(Theme.ink2).controlSize(.small)
                    .accessibilityLabel("Dismiss \(i.title)")
                Spacer()
            }.padding(.leading, 54).padding(.bottom, Spacing.s)
        }
    }

    private var daySection: some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            SectionLabel(title: "Today")
            if entries.isEmpty {
                if loaded {
                    EmptyState(symbol: "sun.max", title: "Nothing on today",
                               text: "Dates arrive from the notices the family shares and from the calendar.")
                }
            } else {
                VStack(spacing: 0) {
                    ForEach(Array(entries.enumerated()), id: \.element.id) { i, e in
                        NavigationLink(value: e) { TimelineRow(time: e.time, symbol: e.symbol, tint: e.tint, title: e.title, sub: e.sub, last: i == entries.count - 1) }.buttonStyle(.plain)
                    }
                }
            }
        }
    }

    // MARK: data

    private func load() async {
        do { brief = try await API.shared.brief(); error = nil } catch { self.error = error.localizedDescription }
        events = (try? await API.shared.calendarUpcoming(days: 7)) ?? []
        errands = (try? await API.shared.errands()) ?? []
        checks = (try? await API.shared.documents())?.checks ?? []
        ideas = (try? await API.shared.suggestions()) ?? []
        low = ((try? await API.shared.money())?.runningLow ?? []).filter { $0.status != "fine" }
        loaded = true
        #if canImport(ActivityKit)
        LiveActivities.sync(errands)
        #endif
    }

    private func decide(_ id: UUID, _ status: String) async {
        let said = await session.doOrKeep(label: "The decision", keep: { Outbox.keep(kind: .decide, target: id, status: status, label: "\(status) a date") }) {
            _ = try await API.shared.decide(id, status, requestId: UUID().uuidString)
        }
        error = said; decided += 1; await load()
    }
}

/// The next thing on the day, large enough to read from across a kitchen.
struct NextUpCard: View {
    let entry: Entry
    var body: some View {
        NavigationLink(value: entry) {
            HStack(spacing: Spacing.m) {
                Glyph(symbol: entry.symbol, tint: entry.tint, size: 46)
                VStack(alignment: .leading, spacing: 3) {
                    Text("Next up · \(entry.time == "any time" || entry.time == nil ? "today" : entry.time!)").font(Theme.font(13, .semibold)).foregroundStyle(entry.tint)
                    Text(entry.title).font(Theme.font(19, .semibold)).foregroundStyle(Theme.ink).lineLimit(3).multilineTextAlignment(.leading)
                    if let sub = entry.sub, !sub.isEmpty { Text(sub).font(Theme.font(13)).foregroundStyle(Theme.ink3).lineLimit(2).multilineTextAlignment(.leading) }
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right").font(Theme.font(12, .semibold)).foregroundStyle(Theme.ink3).accessibilityHidden(true)
            }
            .padding(Spacing.l).frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.card).clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous).stroke(entry.tint.opacity(0.4), lineWidth: 1))
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Next up, \(entry.time ?? ""), \(entry.title)")
    }
}

/// A document that will not outlive a trip, or has already run out.
struct DocumentCheckCard: View {
    let check: DocumentCheck
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) { Image(systemName: "doc.text").font(Theme.font(12, .bold)); Text("Documents").font(Theme.font(13, .semibold)) }.foregroundStyle(Theme.warning)
            Text(check.title).font(Theme.font(16, .semibold)).foregroundStyle(Theme.ink)
            Text(check.why).font(Theme.font(13)).foregroundStyle(Theme.ink2)
        }
        .padding(Spacing.l).frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.warning.opacity(0.10)).clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
        .accessibilityElement(children: .combine)
    }
}

struct WeekStrip: View {
    let days: [Date]
    @Binding var picked: Date
    let marks: Set<Date>
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private static let dow: DateFormatter = { let f = DateFormatter(); f.dateFormat = "EEE"; return f }()
    var body: some View {
        HStack(spacing: 0) {
            ForEach(days, id: \.self) { d in
                let on = Calendar.current.isDate(d, inSameDayAs: picked)
                Button { withAnimation(Motion.spring(reduceMotion)) { picked = d } } label: {
                    VStack(spacing: 6) {
                        Text(Self.dow.string(from: d)).font(Theme.font(11)).foregroundStyle(Theme.ink3)
                        Text(String(Calendar.current.component(.day, from: d))).font(Theme.font(17, .semibold)).foregroundStyle(on ? Theme.primary : Theme.ink)
                        Circle().fill(marks.contains(Calendar.current.startOfDay(for: d)) ? (on ? Theme.primary : Theme.green) : .clear).frame(width: 5, height: 5)
                    }
                    .frame(maxWidth: .infinity, minHeight: 56).padding(.vertical, 6)
                    .background(on ? Theme.primaryTint : .clear).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                }.buttonStyle(.plain)
                .accessibilityLabel(Format.day.string(from: d) + (marks.contains(Calendar.current.startOfDay(for: d)) ? ", has dates" : ""))
                .accessibilityAddTraits(on ? [.isSelected] : [])
            }
        }
        .padding(4).background(Theme.card).clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Theme.line, lineWidth: 0.5))
        .sensoryFeedback(.selection, trigger: picked)
    }
}

#Preview("Today · live shape") {
    TodayView().environmentObject(PreviewData.session())
}


/// A small rounded fact: a symbol and a few words, never wider than the screen.
struct Pill: View {
    let symbol: String
    let text: String
    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: symbol).font(Theme.font(12, .semibold)).foregroundStyle(Theme.primary)
            Text(text).font(Theme.font(13)).foregroundStyle(Theme.ink2).lineLimit(1)
        }
        .padding(.horizontal, 12).padding(.vertical, 7)
        .background(Theme.card).clipShape(Capsule())
        .overlay(Capsule().stroke(Theme.line, lineWidth: 0.5))
    }
}
