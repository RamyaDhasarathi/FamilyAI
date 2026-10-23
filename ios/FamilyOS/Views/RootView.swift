import SwiftUI

/// The shell: five places on a bar of our own, Ask in the middle as the
/// coral orb. Inbox, Search and the profile hang off the pages that need them.
struct RootView: View {
    @EnvironmentObject var session: Session
    @State private var tab = Debug.string("tab").map { $0 == "home" ? "today" : $0 } ?? "today"
    @AppStorage("welcomed") private var welcomed = false

    var body: some View {
        if session.isSignedIn && Debug.string("welcome") == nil {
            ZStack(alignment: .bottom) {
                Group {
                    switch tab {
                    case "family", "life": LifeView()
                    case "ask": AskView()
                    case "memories": MemoriesView()
                    case "inbox": NavigationStack { InboxView() }
                    case "settings": NavigationStack { SettingsView() }
                    default: TodayView()
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                // Content fades out under the bar instead of sitting cut off
                // beneath it: the soft edge the system draws for its own bars.
                LinearGradient(colors: [Theme.paper.opacity(0), Theme.paper.opacity(0.85), Theme.paper], startPoint: .top, endPoint: .bottom)
                    .frame(height: 118).allowsHitTesting(false).ignoresSafeArea(edges: .bottom).accessibilityHidden(true)
                TabBar(tab: $tab)
            }
            .ignoresSafeArea(.keyboard)
            .background(Theme.paper.ignoresSafeArea())
        } else if (!welcomed && session.pastedLink == nil) || Debug.string("welcome") != nil {
            // A link in hand (a debug launch, or the mailed link opened) goes straight to signing in.
            WelcomeView(done: { welcomed = true })
        } else {
            SignInView()
        }
    }
}

struct TabBar: View {
    @Binding var tab: String
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var typeSize
    private let items: [(String, String, String)] = [("today", "sun.max", "Today"), ("family", "person.2", "Family"), ("ask", "", "Ask"),
                                                     ("inbox", "tray", "Inbox"), ("memories", "heart", "Memories")]
    var body: some View {
        GlassGroup(spacing: 24) {
            HStack(spacing: 0) {
                ForEach(items, id: \.0) { key, symbol, label in
                    if key == "ask" {
                        Button { withAnimation(Motion.spring(reduceMotion)) { tab = key } } label: { Orb(size: 54, on: tab == "ask") }
                            .frame(width: 64).accessibilityLabel("Ask").accessibilityAddTraits(tab == key ? [.isSelected, .isButton] : [.isButton])
                    } else {
                        Button { withAnimation(Motion.spring(reduceMotion)) { tab = key } } label: {
                            VStack(spacing: 3) {
                                Image(systemName: symbol).font(.system(size: 20, weight: tab == key ? .semibold : .regular))
                                    .symbolEffect(.bounce, options: reduceMotion ? .speed(0) : .default, value: tab == key && !reduceMotion)
                                if !typeSize.isAccessibilitySize { Text(label).font(Theme.font(10, .medium)).lineLimit(1) }
                            }
                            .foregroundStyle(tab == key ? Theme.primary : Theme.ink2)
                            .frame(maxWidth: .infinity, minHeight: 50)
                        }
                        .accessibilityLabel(label)
                        .accessibilityAddTraits(tab == key ? [.isSelected, .isButton] : [.isButton])
                    }
                }
            }
            .padding(.horizontal, 6).padding(.vertical, 4)
            .glassCapsule(interactive: false)
        }
        .padding(.horizontal, 18).padding(.bottom, 4)
        .sensoryFeedback(.selection, trigger: tab)
    }
}

/// The Ask mark: a coral orb with a spark. Glass on iOS 26, tinted: the
/// one tinted element on the bar, so it is the one that stands out.
struct Orb: View {
    var size: CGFloat = 50
    var on: Bool = false
    var body: some View {
        if #available(iOS 26, *) {
            Image(systemName: "sparkle").font(.system(size: size * 0.36, weight: .bold)).foregroundStyle(.white)
                .frame(width: size, height: size)
                .glassEffect(.regular.tint(Theme.primary).interactive(), in: .circle)
                .shadow(color: Theme.primary.opacity(on ? 0.35 : 0.2), radius: on ? 10 : 6, y: 3)
        } else {
            ZStack {
                Circle().fill(LinearGradient(colors: [Theme.primary.opacity(on ? 0.35 : 0.18), Theme.primary.opacity(0.05)], startPoint: .top, endPoint: .bottom))
                Circle().fill(Theme.primary).padding(size * 0.22)
                Image(systemName: "sparkle").font(.system(size: size * 0.26, weight: .bold)).foregroundStyle(.white)
            }
            .frame(width: size, height: size)
            .shadow(color: Theme.primary.opacity(0.35), radius: on ? 10 : 6, y: 3)
        }
    }
}

/// Room at the bottom for the bar.
struct BarSpace: View { var body: some View { Color.clear.frame(height: 96) } }

/// One line of red at the top of a screen when a call failed, with the
/// server's own words.
struct ErrorLine: View {
    let text: String?
    var body: some View {
        if let text, !text.isEmpty {
            Text(text).font(.footnote).foregroundStyle(Theme.red).padding(.horizontal)
        }
    }
}

enum Format {
    static let day: DateFormatter = { let f = DateFormatter(); f.dateFormat = "EEE d MMM"; return f }()
    static let dayYear: DateFormatter = { let f = DateFormatter(); f.dateFormat = "d MMM yyyy"; return f }()
    static let long: DateFormatter = { let f = DateFormatter(); f.dateFormat = "EEEE, d MMMM"; return f }()
    static let stamp: DateFormatter = { let f = DateFormatter(); f.dateStyle = .medium; f.timeStyle = .short; return f }()
    static let clock: DateFormatter = { let f = DateFormatter(); f.dateFormat = "h:mm a"; return f }()

    static func money(_ amount: Double, _ currency: String) -> String {
        let sym = ["INR": "₹", "USD": "$", "GBP": "£", "EUR": "€", "AED": "AED "][currency.uppercased()] ?? (currency + " ")
        // The amount is written the way its currency's country writes it,
        // not the way the phone's region does: ₹1,940.98 on a phone set to
        // a region that writes 1.940,98 is still ₹1,940.98.
        let f = NumberFormatter(); f.numberStyle = .decimal; f.maximumFractionDigits = amount == amount.rounded() ? 0 : 2; f.minimumFractionDigits = amount == amount.rounded() ? 0 : 2
        f.locale = Locale(identifier: ["INR": "en_IN", "AED": "en_AE", "GBP": "en_GB", "EUR": "en_IE"][currency.uppercased()] ?? "en_US")
        f.usesGroupingSeparator = true
        return sym + (f.string(from: NSNumber(value: amount)) ?? String(amount))
    }

    static func when(_ date: Date?, _ time: String? = nil) -> String? {
        guard let date else { return nil }
        let d = Calendar.current.isDateInToday(date) ? "Today" : Calendar.current.isDateInTomorrow(date) ? "Tomorrow" : day.string(from: date)
        return time.map { "\(d), \(clockText($0))" } ?? d
    }

    /// "08:30" or "08:30 to 12:30" as "8:30 AM".
    static func clockText(_ time: String) -> String {
        let first = time.split(separator: " ").first.map(String.init) ?? time
        let parts = first.split(separator: ":").compactMap { Int($0) }
        guard parts.count >= 2 else { return time }
        let h = parts[0] % 12 == 0 ? 12 : parts[0] % 12
        return String(format: "%d:%02d %@", h, parts[1], parts[0] < 12 ? "AM" : "PM")
    }
}

/// Launch arguments a debug build honours so a script can put a screen on
/// the simulator (`-tab inbox`, `-notice <id>`). Nothing in a release build.
enum Debug {
    static func string(_ key: String) -> String? {
        #if DEBUG
        return UserDefaults.standard.string(forKey: key).flatMap { $0.isEmpty ? nil : $0 }
        #else
        return nil
        #endif
    }
}
