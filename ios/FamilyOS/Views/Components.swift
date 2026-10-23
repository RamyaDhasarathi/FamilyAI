// The reusable pieces every screen is made of: the header, the states a
// list can be in, the row a task is shown as, the badge an agent's work
// carries, and the summary a person approves against. One vocabulary, so
// a thing looks the same on Today, in Ask, and on an errand.
import SwiftUI

// MARK: screen header

/// The top of a root screen: the title, a line under it, the profile on
/// the right (Settings), and room for one more control.
struct ScreenHeader<Trailing: View>: View {
    let title: String
    var subtitle: String? = nil
    var serif: Bool = false
    @ViewBuilder var trailing: Trailing
    @EnvironmentObject private var session: Session

    init(title: String, subtitle: String? = nil, serif: Bool = false, @ViewBuilder trailing: () -> Trailing) {
        self.title = title; self.subtitle = subtitle; self.serif = serif; self.trailing = trailing()
    }

    var body: some View {
        HStack(alignment: .center, spacing: Spacing.m) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(serif ? Theme.font(28, .regular, .serif) : Theme.font(28, .bold)).foregroundStyle(Theme.ink).lineLimit(1).minimumScaleFactor(0.8)
                if let subtitle { Text(subtitle).font(Theme.font(14)).foregroundStyle(Theme.ink3).lineLimit(1) }
            }
            .accessibilityElement(children: .combine).accessibilityAddTraits(.isHeader)
            Spacer(minLength: 0)
            GlassGroup(spacing: 12) {
                HStack(spacing: Spacing.s) {
                    trailing
                    ProfileButton()
                }
            }
        }
        .padding(.top, Spacing.s)
    }
}

extension ScreenHeader where Trailing == EmptyView {
    init(title: String, subtitle: String? = nil, serif: Bool = false) {
        self.init(title: title, subtitle: subtitle, serif: serif) { EmptyView() }
    }
}

/// The person's own face, which is the way to Settings on every screen.
struct ProfileButton: View {
    @EnvironmentObject private var session: Session
    var body: some View {
        NavigationLink(value: "settings") {
            if let m = session.member { Avatar(member: m, size: 40) }
            else { Image(systemName: "person.crop.circle").font(Theme.font(22)).foregroundStyle(Theme.ink).frame(width: 44, height: 44).glassCircle() }
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Settings and profile")
    }
}

/// A round glass control in a header.
struct HeaderButton: View {
    let symbol: String
    let label: String
    let value: String
    var body: some View {
        NavigationLink(value: value) {
            Image(systemName: symbol).font(Theme.font(17, .medium)).foregroundStyle(Theme.ink).frame(width: 44, height: 44).glassCircle()
        }
        .buttonStyle(.plain).accessibilityLabel(label)
    }
}

// MARK: the states a list can be in

/// Nothing here, said kindly, with the one thing that would change that.
struct EmptyState: View {
    let symbol: String
    let title: String
    var text: String? = nil
    var action: (label: String, run: () -> Void)? = nil
    var body: some View {
        VStack(spacing: Spacing.m) {
            Image(systemName: symbol).font(.system(size: 30, weight: .light)).foregroundStyle(Theme.ink3).accessibilityHidden(true)
            VStack(spacing: Spacing.xs) {
                Text(title).font(Theme.font(16, .semibold)).foregroundStyle(Theme.ink).multilineTextAlignment(.center)
                if let text { Text(text).font(Theme.font(14)).foregroundStyle(Theme.ink3).multilineTextAlignment(.center) }
            }
            if let action { Button(action.label, action: action.run).font(Theme.font(15, .semibold)).foregroundStyle(Theme.primary).padding(.top, Spacing.xs) }
        }
        .frame(maxWidth: .infinity).padding(.vertical, Spacing.xl).padding(.horizontal, Spacing.l)
        .background(Theme.card).clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous).stroke(Theme.line, lineWidth: 0.5))
        .accessibilityElement(children: .combine)
    }
}

/// Rows that are still on their way: the shape of the list, greyed, so
/// nothing jumps when the data lands.
struct LoadingRows: View {
    var count: Int = 3
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var on = false
    var body: some View {
        VStack(spacing: Spacing.s) {
            ForEach(0..<count, id: \.self) { i in
                HStack(spacing: Spacing.m) {
                    RoundedRectangle(cornerRadius: 10, style: .continuous).fill(Theme.line).frame(width: 34, height: 34)
                    VStack(alignment: .leading, spacing: 6) {
                        RoundedRectangle(cornerRadius: 4).fill(Theme.line).frame(width: i % 2 == 0 ? 180 : 140, height: 12)
                        RoundedRectangle(cornerRadius: 4).fill(Theme.line).frame(width: 90, height: 10)
                    }
                    Spacer()
                }
                .padding(Spacing.m).background(Theme.card).clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
        }
        .opacity(on || reduceMotion ? 1 : 0.55)
        .animation(reduceMotion ? nil : .easeInOut(duration: 0.9).repeatForever(autoreverses: true), value: on)
        .onAppear { on = true }
        .accessibilityLabel("Loading")
    }
}

/// A call failed: the server's words, and the one button that tries again.
struct ErrorState: View {
    let text: String
    var retry: (() -> Void)? = nil
    var body: some View {
        HStack(alignment: .top, spacing: Spacing.m) {
            Image(systemName: "exclamationmark.circle").font(Theme.font(17, .semibold)).foregroundStyle(Theme.danger).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: Spacing.xs) {
                Text("That did not load").font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                Text(text).font(Theme.font(13)).foregroundStyle(Theme.ink2)
                if let retry { Button("Try again", action: retry).font(Theme.font(14, .semibold)).foregroundStyle(Theme.primary).padding(.top, 2) }
            }
            Spacer(minLength: 0)
        }
        .padding(Spacing.l).frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.danger.opacity(0.08)).clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
        .accessibilityElement(children: .combine)
    }
}

/// The phone had no signal when something was done: it is kept, and goes
/// when the phone is back. Shown wherever the person might wonder.
struct OfflineBanner: View {
    @EnvironmentObject private var session: Session
    var body: some View {
        if session.outboxLeft > 0 {
            HStack(spacing: Spacing.m) {
                Image(systemName: "wifi.slash").foregroundStyle(Theme.warning).accessibilityHidden(true)
                Text("\(session.outboxLeft) thing\(session.outboxLeft == 1 ? "" : "s") kept until the phone is back online").font(Theme.font(13)).foregroundStyle(Theme.ink2)
                Spacer()
                Button("Send now") { Task { await session.flushOutbox() } }.font(Theme.font(13, .semibold)).foregroundStyle(Theme.primary)
            }
            .padding(Spacing.m).background(Theme.warning.opacity(0.12)).clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .accessibilityElement(children: .combine)
        }
    }
}

/// A feature the system has not let the app use. The explanation first,
/// then the one way to change it.
struct PermissionDenied: View {
    let what: String
    let why: String
    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            Label(what, systemImage: "lock").font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
            Text(why).font(Theme.font(13)).foregroundStyle(Theme.ink2)
            if let url = URL(string: UIApplication.openSettingsURLString) {
                Link("Open iPhone Settings", destination: url).font(Theme.font(14, .semibold)).foregroundStyle(Theme.primary)
            }
        }
        .padding(Spacing.l).frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.card).clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous).stroke(Theme.line, lineWidth: 0.5))
    }
}

// MARK: the agent's work

/// Where a piece of the agent's work stands. One vocabulary for an errand,
/// a proposal in Ask, and the Live Activity.
enum AgentState: Equatable {
    case suggested, waitingApproval, planning, working, needsYou, done, failed, stopped, cancelled

    /// From an errand's status on the server.
    init(errand status: String) {
        switch status {
        case "proposed": self = .waitingApproval
        case "approved": self = .planning
        case "running": self = .working
        case "needs_you": self = .needsYou
        case "done": self = .done
        case "failed": self = .failed
        case "stopped": self = .stopped
        case "cancelled": self = .cancelled
        default: self = .suggested
        }
    }

    var label: String {
        switch self {
        case .suggested: return "Suggested"
        case .waitingApproval: return "Needs approval"
        case .planning: return "Approved, starting"
        case .working: return "Working"
        case .needsYou: return "Needs you"
        case .done: return "Done"
        case .failed: return "Failed"
        case .stopped: return "Stopped"
        case .cancelled: return "Cancelled"
        }
    }
    var symbol: String {
        switch self {
        case .suggested: return "sparkle"
        case .waitingApproval: return "hand.raised"
        case .planning: return "clock"
        case .working: return "circle.dotted"
        case .needsYou: return "person.fill.questionmark"
        case .done: return "checkmark.circle.fill"
        case .failed: return "xmark.octagon"
        case .stopped: return "stop.circle"
        case .cancelled: return "minus.circle"
        }
    }
    var tint: Color {
        switch self {
        case .suggested, .planning: return Theme.primary
        case .waitingApproval, .needsYou: return Theme.warning
        case .working: return Space.school.color
        case .done: return Theme.success
        case .failed: return Theme.danger
        case .stopped, .cancelled: return Theme.ink3
        }
    }
    var isLive: Bool { self == .planning || self == .working }
}

/// The badge: a small pill that says the state, moving only while working.
struct AgentStatusBadge: View {
    let state: AgentState
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        HStack(spacing: 5) {
            if state == .working && !reduceMotion {
                ProgressView().controlSize(.mini).tint(state.tint)
            } else {
                Image(systemName: state.symbol).font(.system(size: 11, weight: .semibold))
            }
            Text(state.label).font(Theme.font(12, .semibold))
        }
        .padding(.horizontal, 9).padding(.vertical, 5)
        .foregroundStyle(state.tint).background(state.tint.opacity(0.12)).clipShape(Capsule())
        .accessibilityLabel("Status: \(state.label)")
    }
}

/// What a person is approving: the exact action, who and what it touches,
/// the limit, and what will not happen. Shown before any consequential
/// action; the fingerprint tail ties the approval to this exact text.
struct ApprovalSummary: View {
    struct Line: Identifiable { let id = UUID(); let label: String; let value: String }
    let action: String
    let lines: [Line]
    var affects: [Member] = []
    var never: [String] = []
    var fingerprint: String? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.m) {
            VStack(alignment: .leading, spacing: 2) {
                Text("You are approving").font(Theme.font(12, .semibold)).foregroundStyle(Theme.ink3).textCase(.uppercase)
                Text(action).font(Theme.font(17, .semibold)).foregroundStyle(Theme.ink)
            }
            VStack(spacing: 0) {
                ForEach(lines) { l in
                    HStack(alignment: .firstTextBaseline, spacing: Spacing.m) {
                        Text(l.label).font(Theme.font(13)).foregroundStyle(Theme.ink3).frame(width: 84, alignment: .leading)
                        Text(l.value).font(Theme.font(14, .medium)).foregroundStyle(Theme.ink)
                        Spacer(minLength: 0)
                    }
                    .padding(.vertical, 6)
                    .accessibilityElement(children: .combine)
                    if l.id != lines.last?.id { Divider() }
                }
            }
            if !affects.isEmpty {
                HStack(spacing: Spacing.s) {
                    Text("Affects").font(Theme.font(13)).foregroundStyle(Theme.ink3)
                    ForEach(affects) { m in
                        HStack(spacing: 4) { Avatar(member: m, size: 20); Text(m.displayName.split(separator: " ").first.map(String.init) ?? m.displayName).font(Theme.font(13, .medium)) }
                    }
                }
            }
            if !never.isEmpty {
                VStack(alignment: .leading, spacing: 3) {
                    ForEach(never, id: \.self) { n in
                        Label(n, systemImage: "nosign").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                    }
                }
            }
            if let fingerprint {
                Text("Approval is bound to this exact text · \(fingerprint.prefix(8))").font(Theme.font(11)).foregroundStyle(Theme.ink3)
            }
        }
        .padding(Spacing.l).frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.warning.opacity(0.10)).clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous).stroke(Theme.warning.opacity(0.35), lineWidth: 0.5))
    }
}

// MARK: a task as one row

/// One task or notice as a row: glyph, title, a line of detail, and on the
/// right what the row offers. Every list of things to do is made of this.
struct TaskRow: View {
    enum Trailing { case chevron, none, count(Int), pay(URL), state(AgentState), check(Bool) }
    let symbol: String
    let tint: Color
    let title: String
    var detail: String? = nil
    var trailing: Trailing = .chevron

    var body: some View {
        HStack(spacing: Spacing.m) {
            Glyph(symbol: symbol, tint: tint, size: 34)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink).lineLimit(2).multilineTextAlignment(.leading)
                if let detail, !detail.isEmpty { Text(detail).font(Theme.font(12)).foregroundStyle(Theme.ink3).lineLimit(2).multilineTextAlignment(.leading) }
            }
            Spacer(minLength: Spacing.s)
            switch trailing {
            case .chevron: Image(systemName: "chevron.right").font(Theme.font(12, .semibold)).foregroundStyle(Theme.ink3).accessibilityHidden(true)
            case .none: EmptyView()
            case .count(let n): Text("\(n)").font(Theme.font(11, .semibold)).padding(.horizontal, 7).padding(.vertical, 2).background(Theme.warning.opacity(0.2)).foregroundStyle(Theme.ink2).clipShape(Capsule())
            case .pay(let url): Link(destination: url) { Text("Pay").font(Theme.font(13, .semibold)).padding(.horizontal, 12).padding(.vertical, 6).background(Theme.primaryTint).foregroundStyle(Theme.primary).clipShape(Capsule()) }.accessibilityLabel("Pay \(title)")
            case .state(let s): AgentStatusBadge(state: s)
            case .check(let on): Image(systemName: on ? "checkmark.circle.fill" : "circle").font(Theme.font(22)).foregroundStyle(on ? Theme.success : Theme.ink3).accessibilityHidden(true)
            }
        }
        .padding(.horizontal, Spacing.s).padding(.vertical, 9)
        .frame(minHeight: 44)
        .contentShape(Rectangle())
    }
}

/// Rows in one card, hairlines between, the way Settings groups things.
struct ListCard<Content: View>: View {
    @ViewBuilder let content: Content
    var body: some View { Card(padding: 6) { VStack(spacing: 0) { content } } }
}

struct RowDivider: View {
    var inset: CGFloat = 52
    var body: some View { Divider().padding(.leading, inset) }
}

/// A small section label above a card, with one link on the right.
struct SectionLabel: View {
    let title: String
    var link: String? = nil
    var action: (() -> Void)? = nil
    var body: some View { Heading(title: title, link: link, action: action) }
}
