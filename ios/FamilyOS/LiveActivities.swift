// Starting, updating and ending the errand Live Activity from what the
// app sees. The app has no push for this yet, so the activity moves when
// the app refreshes its errands; it ends itself when an errand is done.
import Foundation
#if canImport(ActivityKit)
import ActivityKit

@MainActor
enum LiveActivities {
    /// Fetch the errands and reconcile: on every return to the foreground,
    /// so an island never outlives what the server says.
    static func refresh() async {
        guard let errands = try? await API.shared.errands() else { return }
        sync(errands)
    }

    /// Reconcile the activities with the errands as they are now.
    static func sync(_ errands: [Errand]) {
        guard ActivityAuthorizationInfo().areActivitiesEnabled else { return }
        // Only what is moving now. A run older than half an hour with no
        // word from the server is over as far as the island is concerned.
        let live = errands.filter(\.isMoving)
        let current = Activity<ErrandActivityAttributes>.activities
        for e in live {
            let state = ErrandActivityAttributes.ContentState(status: e.status, statusLabel: e.statusLabel, step: nil)
            if let a = current.first(where: { $0.attributes.errandId == e.id.uuidString }) {
                Task { await a.update(ActivityContent(state: state, staleDate: Date().addingTimeInterval(1800))) }
            } else {
                let attrs = ErrandActivityAttributes(errandId: e.id.uuidString, title: e.title, service: e.service)
                _ = try? Activity.request(attributes: attrs, content: ActivityContent(state: state, staleDate: Date().addingTimeInterval(1800)))
            }
        }
        // Errands no longer live: end their activity with the final word.
        for a in current where !live.contains(where: { $0.id.uuidString == a.attributes.errandId }) {
            let ended = errands.first { $0.id.uuidString == a.attributes.errandId }
            let final = ended.map { $0.isLive ? "stopped" : $0.status } ?? "done"
            let state = ErrandActivityAttributes.ContentState(status: final, statusLabel: ended.map { $0.isLive ? "no word from the server" : $0.statusLabel } ?? "done", step: nil)
            // A finished run keeps its last word for two minutes; a cancelled,
            // stopped or lost one leaves the island at once.
            let worthAWord = ended.map { $0.status == "done" || $0.status == "failed" } ?? false
            Task { await a.end(ActivityContent(state: state, staleDate: nil), dismissalPolicy: worthAWord ? .after(Date().addingTimeInterval(120)) : .immediate) }
        }
    }
}
#endif
