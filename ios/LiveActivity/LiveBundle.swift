// The errand Live Activity as the lock screen and the Dynamic Island draw it.
import ActivityKit
import SwiftUI
import WidgetKit

@main
struct FamilyOSLiveBundle: WidgetBundle {
    var body: some Widget { ErrandLiveActivity() }
}

struct ErrandLiveActivity: Widget {
    let coral = Color(red: 0.824, green: 0.373, blue: 0.275)

    var body: some WidgetConfiguration {
        ActivityConfiguration(for: ErrandActivityAttributes.self) { context in
            // The lock screen and the banner.
            HStack(spacing: 12) {
                Mark(coral: coral, status: context.state.status)
                VStack(alignment: .leading, spacing: 2) {
                    Text(context.attributes.title).font(.headline).lineLimit(2)
                    Text(line(context)).font(.subheadline).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer()
                StatusPill(label: context.state.statusLabel, status: context.state.status, coral: coral)
            }
            .padding(14)
            .activityBackgroundTint(Color(.systemBackground).opacity(0.85))
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) { Mark(coral: coral, status: context.state.status).padding(.leading, 4) }
                DynamicIslandExpandedRegion(.trailing) { StatusPill(label: context.state.statusLabel, status: context.state.status, coral: coral).padding(.trailing, 4) }
                DynamicIslandExpandedRegion(.center) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(context.attributes.title).font(.headline).lineLimit(1)
                        Text(line(context)).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
                DynamicIslandExpandedRegion(.bottom) {
                    if context.state.status == "needs_you" {
                        Text("It is waiting for you: open FamilyOS to take over.").font(.caption).foregroundStyle(.secondary)
                    }
                }
            } compactLeading: {
                Image(systemName: "sparkle").foregroundStyle(coral)
            } compactTrailing: {
                Text(context.state.statusLabel).font(.caption2).foregroundStyle(context.state.status == "needs_you" ? .orange : .secondary).lineLimit(1)
            } minimal: {
                Image(systemName: context.state.status == "needs_you" ? "exclamationmark.circle.fill" : "sparkle").foregroundStyle(context.state.status == "needs_you" ? .orange : coral)
            }
        }
    }

    private func line(_ context: ActivityViewContext<ErrandActivityAttributes>) -> String {
        [context.attributes.service, context.state.step].compactMap { $0 }.joined(separator: " · ")
    }
}

struct Mark: View {
    let coral: Color; let status: String
    var body: some View {
        ZStack {
            Circle().fill(coral.opacity(0.16))
            Image(systemName: status == "done" ? "checkmark" : status == "needs_you" ? "hand.raised" : "sparkle").font(.system(size: 16, weight: .bold)).foregroundStyle(coral)
        }.frame(width: 38, height: 38)
    }
}

struct StatusPill: View {
    let label: String; let status: String; let coral: Color
    var tint: Color { status == "needs_you" ? .orange : status == "done" ? .green : coral }
    var body: some View {
        Text(label).font(.caption.weight(.semibold)).padding(.horizontal, 9).padding(.vertical, 4)
            .background(tint.opacity(0.15)).foregroundStyle(tint).clipShape(Capsule())
    }
}
