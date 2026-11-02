import Charts
import HealthKit
import SwiftUI

/// Your own Health numbers, if you switch them on. The Health app already holds what the Apple Watch records,
/// so this app reads it from there. Only one summary per day leaves the phone (steps, sleep, resting heart rate,
/// workouts), never individual readings. Nobody else sees it; switching off deletes what the server kept.
@MainActor
final class HealthCenter: ObservableObject {
    static let shared = HealthCenter()

    /// The server's private option. Off for the product: then nothing here is shown, listened to or sent.
    @Published var offered = false
    @Published var sync = false
    @Published var lastDay: String?
    @Published var busy = false
    @Published var said: String?
    @Published var detail: String?
    private let store = HKHealthStore()
    private var observers: [HKObserverQuery] = []
    private var pushing = false          // one send at a time: a wake and an app-open can arrive together
    /// Remembered so a launch the system started in the background knows, before any network call, whether to listen.
    private static let flag = "familyos.health.sync"

    var available: Bool { HKHealthStore.isHealthDataAvailable() }

    private var readTypes: Set<HKObjectType> {
        [HKQuantityType(.stepCount), HKQuantityType(.restingHeartRate), HKCategoryType(.sleepAnalysis), HKObjectType.workoutType()]
    }

    /// At launch and whenever the app opens: learn the switch from the server, then send the days since last time.
    func refresh() async {
        guard Server.token != nil, let s = try? await API.shared.healthSync() else { return }
        offered = s.available
        guard s.available else { sync = false; UserDefaults.standard.set(false, forKey: Self.flag); stopListening(); return }
        sync = s.sync
        lastDay = s.lastDay
        UserDefaults.standard.set(s.sync, forKey: Self.flag)
        s.sync ? listen() : stopListening()
        if s.sync { await push(days: s.lastDay == nil ? 30 : 7); await diagnose() }
    }

    func turnOn() async {
        guard available else { said = "Health data is not available on this device."; return }
        busy = true; defer { busy = false }
        do { try await store.requestAuthorization(toShare: [], read: readTypes) } catch { said = "Health access was not granted: \(error.localizedDescription)"; return }
        do { try await API.shared.setHealthSync(true) } catch { said = "Could not switch it on: \(error.localizedDescription)"; return }
        sync = true; said = nil
        UserDefaults.standard.set(true, forKey: Self.flag)
        listen()
        await push(days: 30)
    }

    /// The server is the source of truth: only when it has deleted what it kept is the switch shown off, so a failed
    /// call cannot leave the phone saying off while the server still holds (and the next open re-enables) the sync.
    func turnOff() async {
        busy = true; defer { busy = false }
        do { try await API.shared.setHealthSync(false) } catch { said = "Could not switch it off: \(error.localizedDescription). It is still on."; return }
        sync = false; lastDay = nil; detail = nil; said = nil
        UserDefaults.standard.set(false, forKey: Self.flag)
        stopListening()
    }

    /// On sign-out: nothing of this person's stays on the phone, and nothing keeps listening for them.
    func reset() {
        stopListening()
        UserDefaults.standard.set(false, forKey: Self.flag)
        sync = false; offered = false; lastDay = nil; detail = nil; said = nil
    }

    /// What the app can actually see, for the Settings footnote: how far back each type is allowed, and the sleep and
    /// workout entries found in the last 30 days (by kind, so a source that writes only "in bed" is visible).
    func diagnose() async {
        guard available else { return }
        let f = DateFormatter(); f.dateFormat = "d MMM"
        var parts: [String] = []
        let named: [(String, HKObjectType)] = [("Steps", HKQuantityType(.stepCount)), ("Heart", HKQuantityType(.restingHeartRate)), ("Sleep", HKCategoryType(.sleepAnalysis)), ("Workouts", HKObjectType.workoutType())]
        if #available(iOS 27.0, *), let dates = try? await store.earliestAuthorizedSampleDate(for: Set(named.map(\.1))) {
            for (name, type) in named { parts.append(dates[type].map { "\(name) from \(f.string(from: $0))" } ?? "\(name) all time") }
        } else {
            parts.append("access dates need iOS 27")
        }
        let start = Date().addingTimeInterval(-30 * 86_400)
        let window = HKQuery.predicateForSamples(withStart: start, end: nil)
        var sleep: [HKCategorySample] = []
        var problem = ""
        do { sleep = try await HKSampleQueryDescriptor(predicates: [.categorySample(type: HKCategoryType(.sleepAnalysis), predicate: window)], sortDescriptors: []).result(for: store) }
        catch { problem = " Sleep read failed: \(error.localizedDescription)." }
        var kinds: [Int: Int] = [:]
        for s in sleep { kinds[s.value, default: 0] += 1 }
        let names = [0: "in bed", 1: "asleep", 2: "awake", 3: "core", 4: "deep", 5: "REM"]
        let seen = kinds.sorted { $0.key < $1.key }.map { "\(names[$0.key] ?? "kind \($0.key)") \($0.value)" }.joined(separator: ", ")
        var works = 0
        do { works = try await HKSampleQueryDescriptor(predicates: [.workout(window)], sortDescriptors: []).result(for: store).count }
        catch { problem += " Workout read failed: \(error.localizedDescription)." }
        detail = "Access: " + parts.joined(separator: " · ") + ". Seen in 30 days: sleep entries \(sleep.isEmpty ? "none" : seen); workouts \(works).\(problem)"
    }

    /// Called as the app launches, including when the system starts it in the background for new Health data.
    func resume() { if UserDefaults.standard.bool(forKey: Self.flag), Server.token != nil { listen() } }

    /// Ask HealthKit to wake the app (at most about hourly) when new steps, sleep, heart rate or workouts arrive,
    /// then send the last few days. The observer queries have to exist from launch for the wake to be delivered.
    private func listen() {
        guard available, observers.isEmpty else { return }
        for type in readTypes.compactMap({ $0 as? HKSampleType }) {
            store.enableBackgroundDelivery(for: type, frequency: .hourly) { _, _ in }
            let q = HKObserverQuery(sampleType: type, predicate: nil) { [weak self] _, done, error in
                guard error == nil, let self else { done(); return }
                Task { @MainActor in
                    await self.push(days: 3)
                    done()
                }
            }
            store.execute(q)
            observers.append(q)
        }
    }

    private func stopListening() {
        for q in observers { store.stop(q) }
        observers = []
        for type in readTypes.compactMap({ $0 as? HKSampleType }) { store.disableBackgroundDelivery(for: type) { _, _ in } }
    }

    private func push(days: Int) async {
        guard available, Server.token != nil, !pushing else { return }
        pushing = true; busy = true
        defer { pushing = false; busy = false }
        let cal = Calendar.current
        let end = cal.startOfDay(for: Date()).addingTimeInterval(86_400)
        guard let start = cal.date(byAdding: .day, value: -days, to: end) else { return }
        do {
            let list = try await summaries(from: start, to: end)
            guard !list.isEmpty else { return }
            try await API.shared.postHealthDaily(list)
            lastDay = list.map(\.day).max()
            said = nil
        } catch { said = "Could not read or send Health data: \(error.localizedDescription)" }
    }

    private static let dayFormat: DateFormatter = { let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; f.locale = Locale(identifier: "en_US_POSIX"); return f }()

    /// One summary per day with anything in it. A type the person did not allow simply comes back empty.
    private func summaries(from start: Date, to end: Date) async throws -> [HealthDay] {
        let cal = Calendar.current
        let window = HKQuery.predicateForSamples(withStart: start, end: end)
        var steps: [Date: Int] = [:], hr: [Date: Int] = [:], sleep: [Date: Int] = [:]
        var workouts: [Date: (n: Int, minutes: Int)] = [:]

        let stepsQuery = HKStatisticsCollectionQueryDescriptor(predicate: .quantitySample(type: HKQuantityType(.stepCount), predicate: window),
                                                               options: .cumulativeSum, anchorDate: start, intervalComponents: DateComponents(day: 1))
        try await stepsQuery.result(for: store).enumerateStatistics(from: start, to: end) { s, _ in
            if let v = s.sumQuantity()?.doubleValue(for: .count()), v > 0 { steps[cal.startOfDay(for: s.startDate)] = Int(v.rounded()) }
        }
        let hrQuery = HKStatisticsCollectionQueryDescriptor(predicate: .quantitySample(type: HKQuantityType(.restingHeartRate), predicate: window),
                                                            options: .discreteAverage, anchorDate: start, intervalComponents: DateComponents(day: 1))
        try await hrQuery.result(for: store).enumerateStatistics(from: start, to: end) { s, _ in
            if let v = s.averageQuantity()?.doubleValue(for: HKUnit.count().unitDivided(by: .minute())), v > 0 { hr[cal.startOfDay(for: s.startDate)] = Int(v.rounded()) }
        }
        // Sleep belongs to the day you woke up. Only the asleep stages count, not time in bed or awake.
        let asleep: Set<Int> = [HKCategoryValueSleepAnalysis.asleepUnspecified.rawValue, HKCategoryValueSleepAnalysis.asleepCore.rawValue,
                                HKCategoryValueSleepAnalysis.asleepDeep.rawValue, HKCategoryValueSleepAnalysis.asleepREM.rawValue]
        let sleepQuery = HKSampleQueryDescriptor(predicates: [.categorySample(type: HKCategoryType(.sleepAnalysis), predicate: window)], sortDescriptors: [])
        for s in try await sleepQuery.result(for: store) where asleep.contains(s.value) {
            sleep[cal.startOfDay(for: s.endDate), default: 0] += Int(s.endDate.timeIntervalSince(s.startDate) / 60)
        }
        let workoutQuery = HKSampleQueryDescriptor(predicates: [.workout(window)], sortDescriptors: [])
        for w in try await workoutQuery.result(for: store) {
            let d = cal.startOfDay(for: w.startDate)
            let now = workouts[d] ?? (0, 0)
            workouts[d] = (now.n + 1, now.minutes + Int(w.duration / 60))
        }
        let days = Set(steps.keys).union(hr.keys).union(sleep.keys).union(workouts.keys)
        return days.sorted().map { d in
            HealthDay(day: Self.dayFormat.string(from: d), steps: steps[d], sleepMinutes: sleep[d].map { min($0, 1440) }, restingHr: hr[d],
                      workouts: min(workouts[d]?.n ?? 0, 50), workoutMinutes: min(workouts[d]?.minutes ?? 0, 1440))
        }
    }
}

/// Settings: the switch, what it sends, and what to do if the system said no.
struct HealthSection: View {
    @ObservedObject var center = HealthCenter.shared
    @Environment(\.scenePhase) private var phase

    var body: some View {
        if center.available && center.offered {
            Section {
                Toggle(isOn: Binding(get: { center.sync }, set: { on in Task { on ? await center.turnOn() : await center.turnOff() } })) {
                    Label("Use my Health summary", systemImage: "heart.text.square")
                }.disabled(center.busy)
                if center.sync, let last = center.lastDay { Text("Latest day sent: \(last)").font(Theme.font(12)).foregroundStyle(Theme.ink3) }
                if center.sync, let d = center.detail { Text(d).font(Theme.font(11)).foregroundStyle(Theme.ink3) }
                if let said = center.said { Text(said).font(Theme.font(12)).foregroundStyle(Theme.warning) }
            } header: { Text("Health") } footer: {
                Text("Reads steps, sleep, resting heart rate and workouts from the Health app, which includes your Apple Watch. One summary per day is sent, never individual readings. Only you can see it, in Ask. It is not medical advice. Switching off deletes what was kept. To change what is shared, use Settings, Health, Data Access in the iPhone.")
            }
            .task { await center.refresh() }
            .onChange(of: phase) { _, now in if now == .active { Task { await center.refresh() } } }
        }
    }
}

/// On the Health page: the last two weeks of your own numbers. Only shown to you, and only while the sync is on.
struct HealthCard: View {
    @ObservedObject var center = HealthCenter.shared
    @State private var rows: [HealthRow] = []
    @State private var loaded = false
    @State private var failed = false

    private static let parse: DateFormatter = { let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; f.locale = Locale(identifier: "en_US_POSIX"); return f }()
    private var days: [(date: Date, row: HealthRow)] {
        rows.compactMap { r in Self.parse.date(from: r.day).map { ($0, r) } }.sorted { $0.date < $1.date }
    }

    var body: some View {
        Group {
            if !center.available || !center.offered { EmptyView() }
            else if !center.sync {
                Card { Text("Switch on “Health device data” on the Family tab to see your steps, sleep and resting heart rate here. Only you can see them.").font(Theme.font(13)).foregroundStyle(Theme.ink3) }
            } else if !loaded {
                Card { HStack(spacing: Spacing.s) { ProgressView(); Text("Loading your numbers").font(Theme.font(13)).foregroundStyle(Theme.ink3) } }
            } else if days.isEmpty {
                Card { Text(failed ? "Could not load your numbers. Pull to refresh, or open the Family tab and check the connection." : "Nothing has arrived yet. Open the Health app to check that FamilyOS may read steps, sleep and heart rate.").font(Theme.font(13)).foregroundStyle(Theme.ink3) }
            } else {
                VStack(spacing: Spacing.m) {
                    chart(title: "Steps", unit: "a day", value: { $0.steps.map(Double.init) }, avg: { String(Int($0).formatted()) }, tint: Theme.primary, bars: true)
                    chart(title: "Sleep", unit: "a night", value: { $0.sleepMinutes.map { Double($0) / 60 } }, avg: { String(format: "%.1f h", $0) }, tint: Space.school.color, bars: true)
                    chart(title: "Resting heart rate", unit: "bpm", value: { $0.restingHr.map(Double.init) }, avg: { String(Int($0.rounded())) }, tint: Theme.danger, bars: false)
                }
            }
        }
        .task { await center.refresh(); await load() }
        .onChange(of: center.lastDay) { _, _ in Task { await load() } }
    }

    private func load() async {
        guard center.sync else { loaded = false; return }
        do { rows = try await API.shared.healthDaily(days: 14); failed = false }
        catch { failed = true }
        loaded = true
    }

    @ViewBuilder private func chart(title: String, unit: String, value: @escaping (HealthRow) -> Double?, avg: (Double) -> String, tint: Color, bars: Bool) -> some View {
        let pts = days.compactMap { d in value(d.row).map { (d.date, $0) } }
        if !pts.isEmpty {
            let mean = pts.map(\.1).reduce(0, +) / Double(pts.count)
            Card {
                VStack(alignment: .leading, spacing: Spacing.s) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(title).font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                        Spacer()
                        Text("\(avg(mean)) \(unit), average").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                    }
                    Chart {
                        ForEach(pts, id: \.0) { p in
                            if bars { BarMark(x: .value("Day", p.0, unit: .day), y: .value(title, p.1)).foregroundStyle(tint.gradient).cornerRadius(3) }
                            else {
                                LineMark(x: .value("Day", p.0, unit: .day), y: .value(title, p.1)).foregroundStyle(tint).interpolationMethod(.monotone)
                                PointMark(x: .value("Day", p.0, unit: .day), y: .value(title, p.1)).foregroundStyle(tint)
                            }
                        }
                        RuleMark(y: .value("Average", mean)).foregroundStyle(Theme.ink3.opacity(0.45)).lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
                    }
                    .chartYScale(domain: .automatic(includesZero: bars))
                    .chartXAxis { AxisMarks(values: .stride(by: .day, count: 3)) { _ in AxisValueLabel(format: .dateTime.day().month(.abbreviated), centered: true).foregroundStyle(Theme.ink3) } }
                    .chartYAxis { AxisMarks(position: .leading) { _ in AxisGridLine().foregroundStyle(Theme.line); AxisValueLabel().foregroundStyle(Theme.ink3) } }
                    .frame(height: 120)
                    .accessibilityLabel("\(title), last two weeks, average \(avg(mean)) \(unit)")
                }
            }
        }
    }
}

/// On the Family tab: the switch for Health device data (the Health app, which holds the Apple Watch's numbers).
/// Yours alone: it is shown only to adults, and nobody else sees what it sends.
struct HealthDeviceCard: View {
    @ObservedObject var center = HealthCenter.shared
    @EnvironmentObject var session: Session
    @Environment(\.scenePhase) private var phase

    var body: some View {
        if center.available, center.offered, session.member?.isChild != true {
            Card {
                VStack(alignment: .leading, spacing: Spacing.s) {
                    HStack(spacing: Spacing.m) {
                        Glyph(symbol: "applewatch", tint: Space.health.color, size: 36)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Health device data").font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                            Text(center.sync ? (center.lastDay.map { "On · latest day sent \($0)" } ?? "On") : "Off").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                        }
                        Spacer(minLength: Spacing.s)
                        Toggle("", isOn: Binding(get: { center.sync }, set: { on in Task { on ? await center.turnOn() : await center.turnOff() } }))
                            .labelsHidden().disabled(center.busy)
                            .accessibilityLabel("Health device data")
                    }
                    Text("Steps, sleep, resting heart rate and workouts from the Health app and your Apple Watch. One summary a day, only yours, never medical advice. Switching off deletes what was kept.")
                        .font(Theme.font(12)).foregroundStyle(Theme.ink3)
                    if center.sync, let d = center.detail { Text(d).font(Theme.font(11)).foregroundStyle(Theme.ink3) }
                    if let said = center.said { Text(said).font(Theme.font(12)).foregroundStyle(Theme.warning) }
                    if center.sync, let url = URL(string: "x-apple-health://") { Link("Open the Health app", destination: url).font(Theme.font(13)) }
                }
            }
            .task { await center.refresh() }
            .onChange(of: phase) { _, now in if now == .active { Task { await center.refresh() } } }
        }
    }
}
