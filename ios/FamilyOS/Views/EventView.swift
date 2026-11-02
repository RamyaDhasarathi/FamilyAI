import SwiftUI

/// An event that is in the calendar: what it is, when, and the notice it most likely
/// came from. The calendar does not record where an event came from, so the notices
/// are matched by the words of the title and offered, not asserted.
struct EventView: View {
    let entry: Entry
    @State private var notices: [InboxRow] = []
    @State private var loaded = false

    private static let time: DateFormatter = { let f = DateFormatter(); f.timeStyle = .short; f.dateStyle = .none; return f }()

    private var when: String {
        guard let s = entry.starts else { return entry.time ?? "" }
        let cal = Calendar.current
        let day = Format.long.string(from: s)
        if entry.allDay {
            if let e = entry.ends, let last = cal.date(byAdding: .day, value: -1, to: e), !cal.isDate(last, inSameDayAs: s) {
                return "\(Format.day.string(from: s)) to \(Format.day.string(from: last)), all day"
            }
            return day + ", all day"
        }
        let end = entry.ends.map { " to " + Self.time.string(from: $0) } ?? ""
        return "\(day), \(Self.time.string(from: s))\(end)"
    }

    private var matches: [InboxRow] {
        let words = entry.title.lowercased().split { !$0.isLetter && !$0.isNumber }.map(String.init).filter { $0.count > 3 }
        guard words.count >= 2 else { return [] }
        let scored = notices.map { n -> (InboxRow, Int) in
            let hay = ([n.headline ?? ""] + n.preview).joined(separator: " ").lowercased()
            return (n, words.filter { hay.contains($0) }.count)
        }
        return scored.filter { $0.1 * 2 >= words.count }.sorted { $0.1 != $1.1 ? $0.1 > $1.1 : $0.0.receivedAt > $1.0.receivedAt }.prefix(3).map(\.0)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.xl) {
                VStack(alignment: .leading, spacing: Spacing.s) {
                    HStack(spacing: 6) { Image(systemName: "calendar").font(Theme.font(12, .bold)); Text("In the calendar").font(Theme.font(13, .semibold)) }
                        .foregroundStyle(entry.tint)
                    Text(entry.title).font(Theme.font(26, .regular, .serif)).foregroundStyle(Theme.ink).multilineTextAlignment(.leading)
                    Text(when).font(Theme.font(16)).foregroundStyle(Theme.ink2)
                }
                if !matches.isEmpty {
                    VStack(alignment: .leading, spacing: Spacing.s) {
                        SectionLabel(title: matches.count == 1 ? "The notice it came from" : "Notices it may have come from")
                        ListCard {
                            ForEach(matches) { n in
                                NavigationLink {
                                    NoticeView(artifactId: n.id, title: n.headline ?? entry.title)
                                } label: {
                                    TaskRow(symbol: "doc.text", tint: Theme.primary, title: n.headline ?? n.fromLabel,
                                            detail: n.fromLabel + " · " + Format.day.string(from: n.receivedAt))
                                }.buttonStyle(.plain)
                                if n.id != matches.last?.id { RowDivider() }
                            }
                        }
                    }
                } else if loaded {
                    Text("No notice in the inbox matches this event, so it was probably added to the calendar directly.").font(Theme.font(13)).foregroundStyle(Theme.ink3)
                }
            }
            .padding(.horizontal, Spacing.gutter).padding(.top, Spacing.xl)
            BarSpace()
        }
        .paper()
        .navigationBarTitleDisplayMode(.inline)
        .task {
            notices = (try? await API.shared.inbox(days: 90, limit: 300)) ?? []
            loaded = true
        }
    }
}
