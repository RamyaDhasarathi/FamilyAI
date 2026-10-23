// Three directions for Today, as named previews to flip between in the
// canvas. Same data, three organising ideas. The one carried into
// TodayView.swift is "Morning Paper" with the day strip from "Day Planner";
// the reasoning is in docs/native-app.md ("The design, 9 Oct 2026").
//
// Preview-only: nothing here is in a shipped screen.
import SwiftUI

// MARK: Direction A — Morning Paper
// A single calm scroll that reads top to bottom like a morning note: a serif
// greeting with one summary line, the next thing up as the hero, what needs
// you, then the day. Priority by position, not by boxes.

struct DirectionMorningPaper: View {
    let brief: Brief
    let events: [CalendarEvent]
    let errands: [Errand]
    @EnvironmentObject var session: Session
    private var today: [Entry] { Entry.merge(brief: brief, events: events, on: Date()) }
    private var waiting: [BriefItem] { brief.items.filter { $0.status == "proposed" } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.xl) {
                ScreenHeader(title: greeting(for: Date()) + ",", subtitle: nil, serif: true) { HeaderButton(symbol: "magnifyingglass", label: "Search", value: "search") }
                VStack(alignment: .leading, spacing: 6) {
                    Text(session.member?.displayName.split(separator: " ").first.map(String.init) ?? brief.displayName).font(Theme.font(28, .regular, .serif)).foregroundStyle(Theme.ink)
                    Text("\(waiting.count) things need you · PTM at 9 · the fee is due Friday").font(Theme.font(15)).foregroundStyle(Theme.ink2)
                }
                if let next = today.first {
                    VStack(alignment: .leading, spacing: Spacing.s) {
                        SectionLabel(title: "Next up")
                        HStack(spacing: Spacing.m) {
                            Glyph(symbol: next.symbol, tint: next.tint, size: 44)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(next.time ?? "").font(Theme.font(13, .semibold)).foregroundStyle(next.tint)
                                Text(next.title).font(Theme.font(18, .semibold)).foregroundStyle(Theme.ink)
                                if let sub = next.sub { Text(sub).font(Theme.font(13)).foregroundStyle(Theme.ink3) }
                            }
                            Spacer()
                        }
                        .padding(Spacing.l).background(Theme.card).clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous).stroke(next.tint.opacity(0.35), lineWidth: 1))
                    }
                }
                VStack(alignment: .leading, spacing: Spacing.s) {
                    SectionLabel(title: "Needs you")
                    ListCard {
                        ForEach(waiting) { i in
                            let (symbol, tint) = kindOf(i)
                            TaskRow(symbol: symbol, tint: tint, title: i.title, detail: i.why, trailing: .none)
                            HStack(spacing: Spacing.s) {
                                Button("Accept") {}.buttonStyle(.borderedProminent).tint(Theme.primary).controlSize(.small)
                                Button("Not this") {}.buttonStyle(.bordered).controlSize(.small)
                                Spacer()
                            }.padding(.leading, 52).padding(.bottom, Spacing.s)
                            if i.id != waiting.last?.id { RowDivider() }
                        }
                    }
                }
                VStack(alignment: .leading, spacing: Spacing.s) {
                    SectionLabel(title: "In progress")
                    ListCard {
                        ForEach(errands) { e in TaskRow(symbol: "cart", tint: Theme.primary, title: e.title, detail: e.service, trailing: .state(AgentState(errand: e.status))) }
                    }
                }
                VStack(alignment: .leading, spacing: Spacing.s) {
                    SectionLabel(title: "Today")
                    VStack(spacing: 0) {
                        ForEach(Array(today.enumerated()), id: \.element.id) { i, e in
                            TimelineRow(time: e.time, symbol: e.symbol, tint: e.tint, title: e.title, sub: e.sub, last: i == today.count - 1)
                        }
                    }
                }
                BarSpace()
            }.padding(.horizontal, Spacing.gutter)
        }
        .paper()
    }
}

// MARK: Direction B — Day Planner
// The calendar is the spine: a week strip first, the picked day's timeline
// dominant, everything else beneath it. Good for a family that lives by the
// clock; weaker at saying what matters most.

struct DirectionDayPlanner: View {
    let brief: Brief
    let events: [CalendarEvent]
    @State private var day = Calendar.current.startOfDay(for: Date())
    private var week: [Date] { (-2...4).compactMap { Calendar.current.date(byAdding: .day, value: $0, to: Calendar.current.startOfDay(for: Date())) } }
    private var entries: [Entry] { Entry.merge(brief: brief, events: events, on: day) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.l) {
                ScreenHeader(title: "Today", subtitle: Format.long.string(from: Date()))
                WeekStrip(days: week, picked: $day, marks: Set(brief.items.compactMap { $0.dueDate.map { Calendar.current.startOfDay(for: $0) } }))
                VStack(spacing: 0) {
                    ForEach(Array(entries.enumerated()), id: \.element.id) { i, e in
                        TimelineRow(time: e.time, symbol: e.symbol, tint: e.tint, title: e.title, sub: e.sub, last: i == entries.count - 1)
                    }
                }
                SectionLabel(title: "Waiting on you")
                ListCard {
                    ForEach(brief.items.filter { $0.status == "proposed" }) { i in
                        let (symbol, tint) = kindOf(i)
                        TaskRow(symbol: symbol, tint: tint, title: i.title, detail: Format.when(i.dueDate, i.dueTime))
                    }
                }
                BarSpace()
            }.padding(.horizontal, Spacing.gutter)
        }
        .paper()
    }
}

// MARK: Direction C — Family Board
// A dashboard: the people first with a count each, then a grid of tiles
// (Today, Needs you, Money, Errands). Everything at once, nothing first.
// Included to see it; it is the crowded one the brief warns against.

struct DirectionFamilyBoard: View {
    let brief: Brief
    let errands: [Errand]
    @EnvironmentObject var session: Session
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.l) {
                ScreenHeader(title: "FamilyOS", subtitle: Format.long.string(from: Date()))
                PeopleRow(members: session.members)
                LazyVGrid(columns: [GridItem(.flexible(), spacing: Spacing.m), GridItem(.flexible(), spacing: Spacing.m)], spacing: Spacing.m) {
                    tile("Today", "calendar", Space.school.color, "\(brief.items.filter { $0.dueDate.map { Calendar.current.isDateInToday($0) } ?? false }.count) things")
                    tile("Needs you", "hand.raised", Theme.warning, "\(brief.items.filter { $0.status == "proposed" }.count) to decide")
                    tile("Money", "banknote", Space.money.color, "₹1,940 above usual")
                    tile("Errands", "cart", Theme.primary, "\(errands.filter { AgentState(errand: $0.status).isLive }.count) running")
                }
                SectionLabel(title: "Everything")
                ListCard {
                    ForEach(brief.items) { i in
                        let (symbol, tint) = kindOf(i)
                        TaskRow(symbol: symbol, tint: tint, title: i.title, detail: i.why)
                        if i.id != brief.items.last?.id { RowDivider() }
                    }
                }
                BarSpace()
            }.padding(.horizontal, Spacing.gutter)
        }
        .paper()
    }
    private func tile(_ title: String, _ symbol: String, _ tint: Color, _ count: String) -> some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            Glyph(symbol: symbol, tint: tint, size: 36)
            Text(title).font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
            Text(count).font(Theme.font(12)).foregroundStyle(Theme.ink3)
        }
        .padding(Spacing.l).frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.card).clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous).stroke(Theme.line, lineWidth: 0.5))
    }
}

#Preview("Morning Paper") {
    NavigationStack { DirectionMorningPaper(brief: PreviewData.brief, events: PreviewData.events, errands: PreviewData.errands) }
        .environmentObject(PreviewData.session())
}

#Preview("Day Planner") {
    NavigationStack { DirectionDayPlanner(brief: PreviewData.brief, events: PreviewData.events) }
        .environmentObject(PreviewData.session())
}

#Preview("Family Board") {
    NavigationStack { DirectionFamilyBoard(brief: PreviewData.brief, errands: PreviewData.errands) }
        .environmentObject(PreviewData.session())
}

#Preview("Morning Paper · dark, large text") {
    NavigationStack { DirectionMorningPaper(brief: PreviewData.brief, events: PreviewData.events, errands: PreviewData.errands) }
        .environmentObject(PreviewData.session())
        .preferredColorScheme(.dark)
        .environment(\.dynamicTypeSize, .accessibility1)
}
