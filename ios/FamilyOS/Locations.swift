import CoreLocation
import SwiftUI

/// Sharing where this phone is with the household's other adults, if the person switched it on.
///
/// Opt-in, per person, in Settings. The phone sends only its latest fix (the server keeps only the
/// latest and deletes it when sharing is switched off) and the system tells the app about a
/// significant move, so the battery is spared. Nothing is sent while the switch is off.
@MainActor
final class LocationCenter: NSObject, ObservableObject, CLLocationManagerDelegate {
    static let shared = LocationCenter()

    @Published var sharing = false
    @Published var status: CLAuthorizationStatus = .notDetermined
    @Published var said: String?
    private let manager = CLLocationManager()

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
        manager.pausesLocationUpdatesAutomatically = true
        status = manager.authorizationStatus
    }

    /// At launch and whenever the app opens: learn the switch from the server, then follow it.
    func refresh() async {
        guard Server.token != nil, let on = try? await API.shared.locationSharing() else { return }
        sharing = on
        status = manager.authorizationStatus
        on ? begin() : end()
    }

    func turnOn() async {
        do { try await API.shared.setLocationSharing(true) } catch { said = "Could not switch it on: \(error.localizedDescription)"; return }
        sharing = true
        said = nil
        if manager.authorizationStatus == .notDetermined { manager.requestWhenInUseAuthorization() } else { begin() }
    }

    func turnOff() async {
        try? await API.shared.setLocationSharing(false)
        sharing = false
        end()
    }

    private func begin() {
        switch manager.authorizationStatus {
        case .authorizedWhenInUse:
            // Ask for Always once, so a move is noticed when the app is closed.
            manager.requestAlwaysAuthorization()
            manager.allowsBackgroundLocationUpdates = false
            manager.requestLocation()
        case .authorizedAlways:
            manager.allowsBackgroundLocationUpdates = true
            manager.startMonitoringSignificantLocationChanges()
            manager.requestLocation()
        default: break
        }
    }

    private func end() {
        manager.stopMonitoringSignificantLocationChanges()
        manager.allowsBackgroundLocationUpdates = false
    }

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        Task { @MainActor in
            self.status = manager.authorizationStatus
            if self.sharing { self.begin() }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let fix = locations.last, fix.horizontalAccuracy >= 0 else { return }
        Task {
            guard Server.token != nil else { return }
            try? await API.shared.postLocation(lat: fix.coordinate.latitude, lon: fix.coordinate.longitude,
                                               accuracy: Int(fix.horizontalAccuracy), at: fix.timestamp)
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {}
}

/// Settings: the switch, what it does, and what to do if the system said no.
struct LocationSection: View {
    @ObservedObject var center = LocationCenter.shared
    @Environment(\.scenePhase) private var phase

    var body: some View {
        Section {
            Toggle(isOn: Binding(get: { center.sharing }, set: { on in Task { on ? await center.turnOn() : await center.turnOff() } })) {
                Label("Share my location", systemImage: "location")
            }
            if center.status == .denied || center.status == .restricted {
                Text("Location is off for FamilyOS in the iPhone's Settings. Turn it on there, then switch this on.").font(Theme.font(13)).foregroundStyle(Theme.warning)
                if let url = URL(string: UIApplication.openSettingsURLString) { Link("Open iPhone Settings", destination: url) }
            } else if center.sharing && center.status == .authorizedWhenInUse {
                Text("Choose “Always” in the iPhone's Settings for FamilyOS to be noticed arriving without opening the app.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
            }
            if let said = center.said { Text(said).font(Theme.font(12)).foregroundStyle(Theme.warning) }
        } header: { Text("Location") } footer: {
            Text("Only you can switch this on. The other adults of your household who share too can see whether you are at home or the office, and are told when you arrive. Only your latest position is kept, never a trail; switching off deletes it. Children are not located.")
        }
        .task { await center.refresh() }
        .onChange(of: phase) { _, now in if now == .active { Task { await center.refresh() } } }
    }
}

/// On the Family tab: where the adults who share are. Shown only to someone who shares too.
struct WhereEveryoneCard: View {
    @ObservedObject var center = LocationCenter.shared
    @State private var here: LocationFamily?
    private static let rel: RelativeDateTimeFormatter = { let f = RelativeDateTimeFormatter(); f.unitsStyle = .short; return f }()

    var body: some View {
        Group {
            if let here, here.sharing, !here.people.isEmpty {
                VStack(alignment: .leading, spacing: Spacing.s) {
                    SectionLabel(title: "Where everyone is")
                    ListCard {
                        ForEach(here.people) { p in
                            row(p)
                            if p.id != here.people.last?.id { RowDivider(inset: 6) }
                        }
                    }
                }
            }
        }
        .task(id: center.sharing) { await load() }
        .refreshable { await load() }
    }

    @ViewBuilder private func row(_ p: LocationFamily.Person) -> some View {
        let line: String = p.waiting ? "Sharing, no position yet"
            : [p.place.map { "At \($0)" } ?? "Away", p.recordedAt.map { Self.rel.localizedString(for: $0, relativeTo: Date()) }].compactMap { $0 }.joined(separator: " · ")
        HStack(spacing: Spacing.m) {
            Image(systemName: p.place != nil ? "house.fill" : "location.fill").font(Theme.font(14)).foregroundStyle(p.stale ? Theme.ink3 : Theme.green).frame(width: 28)
            VStack(alignment: .leading, spacing: 2) {
                Text(p.name.split(separator: " ").first.map(String.init) ?? p.name).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                Text(line).font(Theme.font(12)).foregroundStyle(Theme.ink3)
            }
            Spacer()
            if let lat = p.lat, let lon = p.lon, let url = URL(string: "http://maps.apple.com/?ll=\(lat),\(lon)&q=\(p.name.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? "")") {
                Link(destination: url) { Image(systemName: "map").font(Theme.font(15)).foregroundStyle(Theme.primary).frame(width: 44, height: 44) }.accessibilityLabel("Open \(p.name) in Maps")
            }
        }
        .padding(.horizontal, Spacing.s).padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }

    private func load() async { here = try? await API.shared.locationFamily() }
}
