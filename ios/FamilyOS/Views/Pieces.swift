import SwiftUI

// Pieces shared by Today, Family and the notice screens: the people row,
// what FamilyOS noticed, a brief item as a line, and the one shape a dated
// thing takes on a timeline.

/// Everyone in the household, each a way to their own page.
struct PeopleRow: View {
    let members: [Member]
    @Environment(\.dynamicTypeSize) private var typeSize
    private func line(_ m: Member) -> String { m.isChild ? (m.classLabel.map { "Class \($0)" } ?? "School") : m.role.capitalized }
    var body: some View {
        Card(padding: 12) {
            if typeSize.isAccessibilitySize {
                // Four names across do not fit at accessibility sizes: one per line.
                VStack(spacing: 0) {
                    ForEach(members) { m in
                        NavigationLink(value: m) {
                            HStack(spacing: Spacing.m) {
                                Avatar(member: m, size: 40)
                                Text(m.displayName).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                                Spacer()
                                Text(line(m)).font(Theme.font(12)).foregroundStyle(Theme.ink3)
                            }.padding(.vertical, 8)
                        }.buttonStyle(.plain)
                        .accessibilityLabel("\(m.displayName), \(line(m))")
                        if m.id != members.last?.id { Divider() }
                    }
                }
            } else {
                HStack(alignment: .top, spacing: 0) {
                    ForEach(members) { m in
                        NavigationLink(value: m) {
                            VStack(spacing: 6) {
                                Avatar(member: m, size: 50)
                                Text(m.displayName.split(separator: " ").first.map(String.init) ?? m.displayName).font(Theme.font(12, .medium)).foregroundStyle(Theme.ink).lineLimit(1).minimumScaleFactor(0.8)
                                HStack(spacing: 4) {
                                    Circle().fill(m.isChild ? Space.school.color : Theme.green).frame(width: 6, height: 6)
                                    Text(line(m)).font(Theme.font(10)).foregroundStyle(Theme.ink3).lineLimit(1)
                                }
                            }
                        }
                        .buttonStyle(.plain)
                        .frame(maxWidth: .infinity)
                        .accessibilityLabel("\(m.displayName), \(line(m))")
                    }
                }
            }
        }
    }
}

/// What FamilyOS noticed: two things on the record that collide.
struct NoticedCard: View {
    let item: BriefItem
    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            HStack(spacing: 6) {
                Image(systemName: "sparkle").font(Theme.font(12, .bold))
                Text("FamilyOS noticed").font(Theme.font(13, .semibold))
            }.foregroundStyle(Theme.primary)
            Text(Format.when(item.dueDate).map { "\($0) looks tight." } ?? "Two things collide.").font(Theme.font(17, .semibold)).foregroundStyle(Theme.ink)
            Text("\(item.title) \(Format.when(item.dueDate, item.dueTime).map { "on \($0)" } ?? "") and " + (item.clashes ?? []).joined(separator: "; ") + " overlap.")
                .font(Theme.font(14)).foregroundStyle(Theme.ink2)
            if let id = item.artifactId {
                NavigationLink(value: item) {
                    Text("Show the notice").font(Theme.font(14, .semibold)).foregroundStyle(Theme.ink)
                        .padding(.horizontal, 14).padding(.vertical, 9).background(Theme.card).clipShape(Capsule()).overlay(Capsule().stroke(Theme.line))
                }
                .buttonStyle(.plain).id(id)
            }
        }
        .padding(Spacing.l).frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.primary.opacity(0.07)).clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous).stroke(Theme.primary.opacity(0.25), lineWidth: 0.5))
        .accessibilityElement(children: .combine)
    }
}

/// A brief item as one line in a card.
struct BriefLine: View {
    let item: BriefItem
    var body: some View {
        let (symbol, tint) = kindOf(item)
        let when = [Format.when(item.dueDate, item.dueTime), item.subjectName, item.status == "proposed" ? "proposed" : nil].compactMap { $0 }.joined(separator: " · ")
        if item.action == "pay", let pay = item.payUrl, let url = URL(string: pay) {
            TaskRow(symbol: symbol, tint: tint, title: item.title, detail: when, trailing: .pay(url))
        } else {
            TaskRow(symbol: symbol, tint: tint, title: item.title, detail: when)
        }
    }
}

/// One thing on a day: a dated item from the brief or an event from the
/// calendar, in one shape for the timeline.
struct Entry: Identifiable, Hashable {
    let id: String
    let time: String?
    let sortKey: String
    let symbol: String
    let tint: Color
    let title: String
    let sub: String?
    let artifactId: UUID?

    static func merge(brief: Brief?, events: [CalendarEvent], on day: Date) -> [Entry] {
        let cal = Calendar.current
        var out: [Entry] = []
        for i in brief?.items ?? [] where i.dueDate.map({ cal.isDate($0, inSameDayAs: day) }) ?? false {
            let (symbol, tint) = kindOf(i)
            let t = i.dueTime.map(Format.clockText)
            out.append(Entry(id: i.id, time: t ?? "any time", sortKey: i.dueTime.map { String($0.prefix(5)) } ?? "99", symbol: symbol, tint: tint,
                             title: i.title, sub: [i.subjectName, i.why].compactMap { $0 }.first, artifactId: i.artifactId))
        }
        // The calendar holds what was accepted from the notices, so an event
        // with a brief item's title on the same day is that item, not a second one.
        let titles = Set(out.map { $0.title.lowercased().trimmingCharacters(in: .whitespaces) })
        for e in events where (cal.isDate(e.startsAt, inSameDayAs: day) || (e.allDay && e.startsAt <= day && e.endsAt > day))
            && !titles.contains(e.summary.lowercased().trimmingCharacters(in: .whitespaces)) {
            let t = e.allDay ? nil : Format.clock.string(from: e.startsAt)
            let key = e.allDay ? "00" : { let f = DateFormatter(); f.dateFormat = "HH:mm"; return f.string(from: e.startsAt) }()
            out.append(Entry(id: e.id.uuidString, time: t ?? "all day", sortKey: key, symbol: "calendar", tint: Space.travel.color, title: e.summary, sub: "In the calendar", artifactId: nil))
        }
        return out.sorted { $0.sortKey < $1.sortKey }
    }

    /// The first thing still ahead on a day that is today; the first thing on any other day.
    static func next(in entries: [Entry], day: Date) -> Entry? {
        guard Calendar.current.isDateInToday(day) else { return entries.first }
        let f = DateFormatter(); f.dateFormat = "HH:mm"
        let now = f.string(from: Date())
        return entries.first { $0.sortKey >= now && $0.sortKey != "99" } ?? entries.first { $0.sortKey == "99" } ?? entries.last
    }
}
