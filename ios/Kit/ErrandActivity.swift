// The shape of an errand's Live Activity: what the lock screen and the
// Dynamic Island show while FamilyOS runs something for the family. Shared
// by the app, which starts and updates it, and the widget extension, which
// draws it.
import Foundation
#if canImport(ActivityKit)
import ActivityKit

public struct ErrandActivityAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        public var status: String          // running, needs_you, done, failed, stopped, cancelled
        public var statusLabel: String     // "running", "needs you", "done"
        public var step: String?           // the step the runner is on, when it says
        public init(status: String, statusLabel: String, step: String?) { self.status = status; self.statusLabel = statusLabel; self.step = step }
    }
    public var errandId: String
    public var title: String
    public var service: String
    public init(errandId: String, title: String, service: String) { self.errandId = errandId; self.title = title; self.service = service }
}
#endif
