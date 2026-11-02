import BackgroundTasks
import SwiftUI
import UserNotifications

/// Reminders on this phone, with Done and Snooze on the banner.
///
/// No push service is involved: a free developer account cannot have one (Apple's
/// "Supported capabilities" lists Push Notifications under the paid programme), and
/// reminders are known days ahead anyway. The server says what is coming for the next
/// fortnight (`GET /v1/reminders/phone`), the phone schedules each as a local
/// notification at eight in the morning of its day, and asks again whenever the app
/// opens and now and then in the background. What the server learns after the last ask
/// reaches the phone at the next ask; mail and Telegram still go on time.
///
/// Done on a banner marks the notice done (or keeps that for when the phone is back
/// online); Snooze moves the banner by an hour or to tomorrow morning. Nothing is
/// asked of the person until they switch it on in Settings, and the system's own
/// permission is requested then, with the reason beside it.
@MainActor
final class ReminderCenter: NSObject, ObservableObject, UNUserNotificationCenterDelegate {
    static let shared = ReminderCenter()

    static let category = "REMINDER"
    static let done = "REMINDER_DONE"
    static let snoozeHour = "REMINDER_SNOOZE_HOUR"
    static let snoozeTomorrow = "REMINDER_SNOOZE_TOMORROW"
    static let nudgeTodo = "NUDGE_TODO"
    static let nudgeLow = "NUDGE_LOW"
    static let nudgeAdd = "NUDGE_ADD"
    static let nudgeNo = "NUDGE_NO"
    static let nudgeReorder = "NUDGE_REORDER"
    static let nudgeLowBuy = "NUDGE_LOW_BUY"
    static let nudgeBuy = "NUDGE_BUY"
    private static let nudgeHour = 9
    static let taskId = (Bundle.main.bundleIdentifier ?? "com.example.familyos") + ".reminders"      // matches BGTaskSchedulerPermittedIdentifiers in Info.plist
    private static let eveningHour = 18     // the second banner, on the day something is due
    private static let hour = 8              // the hour a reminder fires, local time
    private static let limit = 55            // the system keeps 64 pending; some are left for snoozes

    @Published var enabled = UserDefaults.standard.bool(forKey: "remindersOnPhone")
    @Published var authorization: UNAuthorizationStatus = .notDetermined
    @Published var scheduled = 0
    @Published var opened: UUID?             // a banner was tapped: the notice to show
    @Published var testResult: String?       // what the last test banner did, in words
    @Published var settingsLine = ""        // what the system says about this app's notifications

    private var center: UNUserNotificationCenter { .current() }

    // MARK: setup

    /// At launch, before anything can be tapped: the actions and the delegate.
    func prepare() {
        let done = UNNotificationAction(identifier: Self.done, title: "Done", options: [])
        let hour = UNNotificationAction(identifier: Self.snoozeHour, title: "Snooze 1 hour", options: [])
        let tomorrow = UNNotificationAction(identifier: Self.snoozeTomorrow, title: "Tomorrow morning", options: [])
        let add = UNNotificationAction(identifier: Self.nudgeAdd, title: "Add to to-dos", options: [])
        let no = UNNotificationAction(identifier: Self.nudgeNo, title: "Not now", options: [])
        let reorder = UNNotificationAction(identifier: Self.nudgeReorder, title: "Reorder", options: [.foreground])
        let buy = UNNotificationAction(identifier: Self.nudgeBuy, title: "Ask to buy", options: [])
        center.setNotificationCategories([
            UNNotificationCategory(identifier: Self.nudgeLowBuy, actions: [buy, reorder, no], intentIdentifiers: [], options: []),
            UNNotificationCategory(identifier: Self.category, actions: [done, hour, tomorrow], intentIdentifiers: [], options: []),
            UNNotificationCategory(identifier: Self.nudgeTodo, actions: [add, no], intentIdentifiers: [], options: []),
            UNNotificationCategory(identifier: Self.nudgeLow, actions: [reorder, no], intentIdentifiers: [], options: []),
        ])
        center.delegate = self
        BGTaskScheduler.shared.register(forTaskWithIdentifier: Self.taskId, using: nil) { task in
            Task { @MainActor in
                Self.scheduleRefresh()
                await Self.shared.sync()
                task.setTaskCompleted(success: true)
            }
        }
        Task { await refreshAuthorization() }
    }

    func refreshAuthorization() async {
        let s = await center.notificationSettings()
        authorization = s.authorizationStatus
        func word(_ x: UNNotificationSetting) -> String { x == .enabled ? "on" : x == .disabled ? "off" : "n/a" }
        let status: String
        switch s.authorizationStatus {
        case .authorized: status = "allowed"; case .denied: status = "denied"; case .provisional: status = "provisional"
        case .ephemeral: status = "ephemeral"; default: status = "not asked yet"
        }
        settingsLine = "iPhone says: \(status) · banners \(word(s.alertSetting)) · lock screen \(word(s.lockScreenSetting)) · notification centre \(word(s.notificationCenterSetting)) · sounds \(word(s.soundSetting))"
    }

    static func scheduleRefresh() {
        let request = BGAppRefreshTaskRequest(identifier: taskId)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 6 * 3600)
        try? BGTaskScheduler.shared.submit(request)
    }

    // MARK: switching it on and off

    /// Asked for in Settings, where the reason is written beside the switch.
    func turnOn() async {
        let granted = (try? await center.requestAuthorization(options: [.alert, .sound, .badge])) ?? false
        await refreshAuthorization()
        enabled = granted
        UserDefaults.standard.set(granted, forKey: "remindersOnPhone")
        if granted { Self.scheduleRefresh(); await sync() }
    }

    func turnOff() async {
        enabled = false
        UserDefaults.standard.set(false, forKey: "remindersOnPhone")
        center.removeAllPendingNotificationRequests()
        scheduled = 0
    }

    // MARK: syncing with the server

    /// Make the phone's pending reminders match what the server says is coming.
    func sync() async {
        guard enabled, Server.token != nil, let feed = try? await API.shared.phoneReminders() else { return }
        await refreshAuthorization()
        guard authorization == .authorized || authorization == .provisional else { return }
        let cal = Calendar.current
        let now = Date()
        var fired = Set(UserDefaults.standard.stringArray(forKey: "remindersFired") ?? [])
        var wanted: [(String, Date, PhoneReminder)] = []
        for r in feed {
            guard fired.contains(r.key) == false else { continue }
            var at = cal.date(bySettingHour: Self.hour, minute: 0, second: 0, of: r.fireOn) ?? r.fireOn
            if at <= now {
                // Its hour has gone. A reminder for today the phone has not told yet goes out in a minute, once.
                guard cal.isDate(r.fireOn, inSameDayAs: now) else { fired.insert(r.key); continue }
                at = now.addingTimeInterval(60)
            }
            wanted.append((r.key, at, r))
        }
        wanted.sort { $0.1 < $1.1 }
        let keep = Set(wanted.prefix(Self.limit).map { "rem:" + $0.0 })
        // Pending ones that are no longer wanted (done, dismissed, moved): take them away. Snoozes stay.
        let pending = await center.pendingNotificationRequests()
        center.removePendingNotificationRequests(withIdentifiers: pending.map(\.identifier).filter { $0.hasPrefix("rem:") && !keep.contains($0) })
        let have = Set(pending.map(\.identifier))
        for (key, at, r) in wanted.prefix(Self.limit) where !have.contains("rem:" + key) {
            let content = UNMutableNotificationContent()
            content.title = r.title
            content.body = r.body
            content.sound = .default
            content.categoryIdentifier = Self.category
            content.threadIdentifier = r.artifactId.uuidString
            content.userInfo = ["artifactId": r.artifactId.uuidString, "obligationId": r.obligationId.uuidString, "key": r.key, "title": r.title, "body": r.body]
            let parts = cal.dateComponents([.year, .month, .day, .hour, .minute, .second], from: at)
            try? await center.add(UNNotificationRequest(identifier: "rem:" + key, content: content, trigger: UNCalendarNotificationTrigger(dateMatching: parts, repeats: false)))
            // Once it is in the system's hands it is not made again, even after it has fired.
            fired.insert(key)
        }
        // The evening of the day it is due, a second banner for what nobody has said Done to.
        // It goes when the obligation leaves the feed (done, dismissed or handled elsewhere),
        // and when Done is pressed on any banner for it.
        let live = Set(feed.map { $0.obligationId.uuidString })
        let pendingNow = await center.pendingNotificationRequests().map(\.identifier)
        center.removePendingNotificationRequests(withIdentifiers: pendingNow.filter { $0.hasPrefix("esc:") && !$0.hasPrefix("esc:day:") && !live.contains(String($0.dropFirst(4))) })
        // Several things open on one evening are one banner, not a stack of identical ones: "5 things still open today", the first
        // three named. One or two keep their own banner, with Done and Snooze on it.
        let tonight = feed.filter { cal.isDate($0.fireOn, inSameDayAs: $0.dueDate) }
        var summaries = Set<String>()
        for (_, items) in Dictionary(grouping: tonight, by: { cal.startOfDay(for: $0.dueDate) }) {
            guard let day = items.first?.dueDate, let evening = cal.date(bySettingHour: Self.eveningHour, minute: 0, second: 0, of: day), evening > now else { continue }
            let parts = cal.dateComponents([.year, .month, .day, .hour, .minute], from: evening)
            if items.count > 2 {
                let id = "esc:day:" + String(Int(cal.startOfDay(for: day).timeIntervalSince1970))
                summaries.insert(id)
                // Made again each time: what it says (how many, which) is as of this sync, not as of the one that first scheduled it.
                center.removePendingNotificationRequests(withIdentifiers: items.map { "esc:" + $0.obligationId.uuidString } + [id])
                let content = UNMutableNotificationContent()
                content.title = "\(items.count) things still open today"
                content.body = items.prefix(3).map(\.title).joined(separator: " · ") + (items.count > 3 ? " …" : "")
                content.sound = .default
                content.threadIdentifier = "esc:day"
                try? await center.add(UNNotificationRequest(identifier: id, content: content, trigger: UNCalendarNotificationTrigger(dateMatching: parts, repeats: false)))
                continue
            }
            for r in items where !pendingNow.contains("esc:" + r.obligationId.uuidString) {
                let content = UNMutableNotificationContent()
                // A title that already says it is open ("Still to decide: ...") is not prefixed twice.
                let title = r.title.lowercased().hasPrefix("still ") ? r.title : "Still open: " + r.title
                content.title = title
                content.body = "Due today. Press and hold to mark it done or move it."
                content.sound = .default
                content.categoryIdentifier = Self.category
                content.threadIdentifier = r.artifactId.uuidString
                content.userInfo = ["artifactId": r.artifactId.uuidString, "obligationId": r.obligationId.uuidString, "key": "esc:" + r.key, "title": title, "body": content.body]
                try? await center.add(UNNotificationRequest(identifier: "esc:" + r.obligationId.uuidString, content: content, trigger: UNCalendarNotificationTrigger(dateMatching: parts, repeats: false)))
            }
        }
        // A day's summary that this sync did not make is stale: its things were done, dismissed or are two or fewer now (each has its own banner).
        center.removePendingNotificationRequests(withIdentifiers: pendingNow.filter { $0.hasPrefix("esc:day:") && !summaries.contains($0) })
        await syncNudges(cal: cal, now: now)
        UserDefaults.standard.set(Array(fired.suffix(2000)), forKey: "remindersFired")
        scheduled = await center.pendingNotificationRequests().count
    }

    /// Nudges: a to-do an event implies, and something the household is about to run out of. One banner each,
    /// at nine in the morning of the day it matters, with the answer on the banner. Nothing is added or bought
    /// by a banner: Add makes a to-do, Reorder opens the shop's own search, Not now is remembered.
    private func syncNudges(cal: Calendar, now: Date) async {
        var dismissed = Set(UserDefaults.standard.stringArray(forKey: "nudgesDismissed") ?? [])
        var firedNudges = Set(UserDefaults.standard.stringArray(forKey: "nudgesFired") ?? [])
        var wanted: [(String, Date, UNMutableNotificationContent)] = []
        func at(_ day: Date) -> Date? {
            let nine = cal.date(bySettingHour: Self.nudgeHour, minute: 0, second: 0, of: day) ?? day
            if nine > now { return nine }
            return cal.isDate(day, inSameDayAs: now) ? now.addingTimeInterval(120) : nil
        }
        if let ideas = try? await API.shared.suggestions() {
            for s in ideas {
                let id = "nudge:todo:" + s.key
                guard !firedNudges.contains(id), let when = at(max(s.dueDate, cal.startOfDay(for: now))) else { continue }
                let c = UNMutableNotificationContent()
                c.title = s.title
                c.body = s.why
                c.sound = .default
                c.categoryIdentifier = Self.nudgeTodo
                c.userInfo = ["suggestion": s.key]
                wanted.append((id, when, c))
            }
        }
        let payments = try? await API.shared.paymentsStatus()
        if let money = try? await API.shared.money() {
            let day = API.dayOnly.string(from: now)
            for r in money.runningLow where r.status == "soon" || r.status == "overdue" {
                let id = "nudge:low:\(r.itemKey):" + API.dayOnly.string(from: r.expectedOn)
                guard !firedNudges.contains(id), !dismissed.contains(id), let when = at(cal.startOfDay(for: now)) else { continue }
                let c = UNMutableNotificationContent()
                c.title = "\(r.item) may be running low"
                c.body = "Bought about every \(r.everyDays) days at \(r.merchant); last on \(Format.day.string(from: r.lastOn))."
                c.sound = .default
                // With payments on and a last price known, the banner can ask a guardian to buy it: one purchase, approved first.
                let canAsk = payments?.enabled == true && r.reorderUrl != nil && (r.lastAmount ?? 0) > 0 && Double(payments?.paymentLimit ?? 0) >= (r.lastAmount ?? 0)
                c.categoryIdentifier = r.reorderUrl == nil ? Self.nudgeTodo : (canAsk ? Self.nudgeLowBuy : Self.nudgeLow)
                c.userInfo = ["lowKey": id, "url": r.reorderUrl ?? "", "item": r.item, "merchant": r.merchant, "amount": r.lastAmount ?? 0, "currency": r.currency ?? "INR"]
                _ = day
                wanted.append((id, when, c))
            }
        }
        let live = Set(wanted.map(\.0))
        let pending = await center.pendingNotificationRequests().map(\.identifier)
        center.removePendingNotificationRequests(withIdentifiers: pending.filter { $0.hasPrefix("nudge:") && !live.contains($0) })
        for (id, when, content) in wanted.prefix(8) where !pending.contains(id) {
            let parts = cal.dateComponents([.year, .month, .day, .hour, .minute, .second], from: when)
            try? await center.add(UNNotificationRequest(identifier: id, content: content, trigger: UNCalendarNotificationTrigger(dateMatching: parts, repeats: false)))
            firedNudges.insert(id)
        }
        dismissed = dismissed.filter { !$0.isEmpty }
        UserDefaults.standard.set(Array(firedNudges.suffix(1000)), forKey: "nudgesFired")
        UserDefaults.standard.set(Array(dismissed.suffix(1000)), forKey: "nudgesDismissed")
    }

    /// A test banner in a few seconds, to see the buttons work.
    func sendTest() async {
        await refreshAuthorization()
        guard authorization == .authorized || authorization == .provisional else {
            testResult = "Not sent: the iPhone has not allowed notifications for FamilyOS."
            return
        }
        let content = UNMutableNotificationContent()
        content.title = "A test reminder"
        content.body = "Try Done and Snooze: press and hold this banner."
        content.sound = .default
        content.categoryIdentifier = Self.category
        content.userInfo = ["test": true]
        do {
            try await center.add(UNNotificationRequest(identifier: "snz:test:\(UUID().uuidString)", content: content, trigger: UNTimeIntervalNotificationTrigger(timeInterval: 5, repeats: false)))
            testResult = "Scheduled for 5 seconds from now at \(Date().addingTimeInterval(5).formatted(date: .omitted, time: .standard)). Banners show on the lock screen or inside any app; leave this screen if you see nothing."
        } catch {
            testResult = "The system refused it: \(error.localizedDescription)"
        }
    }

    // MARK: the banner

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification) async -> UNNotificationPresentationOptions {
        [.banner, .list, .sound]
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse) async {
        let info = response.notification.request.content.userInfo
        let artifact = (info["artifactId"] as? String).flatMap(UUID.init)
        switch response.actionIdentifier {
        case Self.done:
            guard let artifact else { return }
            await ReminderCenter.markDone(artifact)
            if let ob = info["obligationId"] as? String { center.removePendingNotificationRequests(withIdentifiers: ["esc:" + ob]) }
            center.removeDeliveredNotifications(withIdentifiers: [response.notification.request.identifier])
        case Self.snoozeHour:
            await ReminderCenter.snooze(response.notification.request.content, seconds: 3600)
        case Self.snoozeTomorrow:
            await ReminderCenter.snooze(response.notification.request.content, seconds: nil)
        case Self.nudgeAdd:
            if let key = info["suggestion"] as? String { try? await API.shared.acceptSuggestion(key) }
        case Self.nudgeNo:
            if let key = info["suggestion"] as? String { try? await API.shared.dismissSuggestion(key) }
            if let low = info["lowKey"] as? String {
                var d = Set(UserDefaults.standard.stringArray(forKey: "nudgesDismissed") ?? []); d.insert(low)
                UserDefaults.standard.set(Array(d), forKey: "nudgesDismissed")
            }
        case Self.nudgeBuy:
            if let url = info["url"] as? String, let item = info["item"] as? String, let merchant = info["merchant"] as? String, let amount = info["amount"] as? Double, amount > 0 {
                try? await API.shared.requestPurchase(title: "Reorder " + item, merchant: merchant, url: url, amount: amount, currency: (info["currency"] as? String) ?? "INR")
            }
        case Self.nudgeReorder:
            if let url = (info["url"] as? String).flatMap(URL.init(string:)), url.scheme?.hasPrefix("http") == true {
                await MainActor.run { UIApplication.shared.open(url) }
            }
        case UNNotificationDefaultActionIdentifier:
            if let artifact { await MainActor.run { ReminderCenter.shared.opened = artifact } }
        default:
            break
        }
    }

    /// Done from the banner: the notice is marked done, with the phone's own words; kept for later when offline.
    nonisolated static func markDone(_ artifact: UUID) async {
        guard Server.token != nil else { return }
        let id = UUID().uuidString
        do { _ = try await API.shared.handled(artifact, note: "done from a reminder on the phone", requestId: id) }
        catch where Outbox.isTransient(error) {
            Outbox.keep(kind: .handled, target: artifact, note: "done from a reminder on the phone", label: "a reminder marked done")
        } catch {}
    }

    /// Snooze: the same words again, an hour on or tomorrow at eight. `seconds` nil means tomorrow morning.
    nonisolated static func snooze(_ original: UNNotificationContent, seconds: TimeInterval?) async {
        let content = UNMutableNotificationContent()
        content.title = original.title
        content.body = original.body
        content.sound = .default
        content.categoryIdentifier = original.categoryIdentifier
        content.threadIdentifier = original.threadIdentifier
        content.userInfo = original.userInfo
        let trigger: UNNotificationTrigger
        if let seconds {
            trigger = UNTimeIntervalNotificationTrigger(timeInterval: seconds, repeats: false)
        } else {
            let cal = Calendar.current
            let tomorrow = cal.date(byAdding: .day, value: 1, to: Date()) ?? Date().addingTimeInterval(86400)
            let at = cal.date(bySettingHour: hour, minute: 0, second: 0, of: tomorrow) ?? tomorrow
            trigger = UNCalendarNotificationTrigger(dateMatching: cal.dateComponents([.year, .month, .day, .hour, .minute], from: at), repeats: false)
        }
        try? await UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: "snz:\(UUID().uuidString)", content: content, trigger: trigger))
    }
}

/// The delegate has to be in place before the app finishes launching, or a tap on a banner that
/// started the app is lost.
final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        MainActor.assumeIsolated { ReminderCenter.shared.prepare(); HealthCenter.shared.resume() }
        return true
    }
}

/// Settings: the switch, the reason, what to do if the system said no.
struct RemindersSection: View {
    @ObservedObject var center = ReminderCenter.shared
    @Environment(\.scenePhase) private var phase
    /// Where else reminders arrive ("Mail and Telegram"), said once in the footer instead of as a section of its own.
    var alsoSentBy: String? = nil

    var body: some View {
        Section {
            Toggle(isOn: Binding(get: { center.enabled }, set: { on in Task { on ? await center.turnOn() : await center.turnOff() } })) {
                Label("Remind me on this phone", systemImage: "bell.badge")
            }
            if center.authorization == .denied {
                Text("Notifications are off for FamilyOS in the iPhone's Settings. Turn them on there, then switch this on.").font(Theme.font(13)).foregroundStyle(Theme.warning)
                if let url = URL(string: UIApplication.openSettingsURLString) { Link("Open iPhone Settings", destination: url) }
            }
            if center.enabled {
                Text("\(center.scheduled) waiting on this phone").font(Theme.font(13)).foregroundStyle(Theme.ink3)
                Button("Send a test banner") { Task { await center.sendTest() } }
                if let r = center.testResult { Text(r).font(Theme.font(12)).foregroundStyle(Theme.ink2) }
            }
            Text("If a Focus such as Reduce Interruptions is on, add FamilyOS to its allowed apps or reminders will wait silently in the notification centre.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
            if !center.settingsLine.isEmpty { Text(center.settingsLine).font(Theme.font(12)).foregroundStyle(Theme.ink3) }
        } header: { Text("Notifications") } footer: {
            Text("A banner at eight in the morning for what is due soon, with Done and Snooze on it. The phone keeps its own list for the next fortnight and refreshes it whenever the app opens or the system lets it. "
                 + (alsoSentBy.map { "Reminders also reach you by \($0), the way the household chose on the console, on time as before. " } ?? "Mail and Telegram reminders go on time as before. ")
                 + "Banners come from this phone's own list, not a push service: that needs Apple's paid developer programme. The day's brief is on Today.")
        }
        .task { await center.refreshAuthorization() }
        .onChange(of: phase) { _, now in if now == .active { Task { await center.refreshAuthorization() } } }
    }
}
