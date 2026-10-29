import SwiftUI

/// One person's prescriptions, newest first. Each is a card: where and by whom, when, then its medicines.
struct PrescriptionsBlock: View {
    let person: PrescriptionsOf
    var members: [Member] = []
    var changed: () async -> Void = {}
    private static let day: DateFormatter = { let f = DateFormatter(); f.dateFormat = "d MMM yyyy"; return f }()

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            Text(person.name ?? "Not matched to anyone").font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink2)
            ForEach(person.prescriptions) { rx in
                Card(padding: 0) {
                    VStack(alignment: .leading, spacing: 0) {
                        NavigationLink(value: rx.artifactId) {
                            HStack(alignment: .top, spacing: Spacing.m) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(rx.clinic ?? "Clinic not read").font(Theme.font(15, .semibold)).foregroundStyle(rx.clinic == nil ? Theme.ink3 : Theme.ink)
                                    Text([rx.prescriber, Self.day.string(from: rx.date)].compactMap { $0 }.joined(separator: " · ")).font(Theme.font(13)).foregroundStyle(Theme.ink3)
                                }
                                Spacer(minLength: Spacing.s)
                                badge(rx.status)
                                if !members.isEmpty {
                                    Menu {
                                        ForEach(members) { m in
                                            Button(m.displayName) { Task { try? await API.shared.setPrescriptionPatient(rx.artifactId, to: m.id); await changed() } }
                                        }
                                    } label: {
                                        Image(systemName: "person.crop.circle.badge.questionmark").font(Theme.font(17)).foregroundStyle(Theme.ink3).frame(width: 44, height: 44)
                                    }.accessibilityLabel("Change whose prescription this is")
                                }
                                Image(systemName: "chevron.right").font(Theme.font(12, .semibold)).foregroundStyle(Theme.ink3).accessibilityHidden(true)
                            }
                            .padding(Spacing.m).contentShape(Rectangle())
                        }.buttonStyle(.plain)
                        ForEach(rx.medicines) { m in
                            Divider().padding(.leading, Spacing.m)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(m.drug + (m.doseText.map { " · " + $0 } ?? "")).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                                let detail = m.line
                                if !detail.isEmpty { Text(detail).font(Theme.font(12)).foregroundStyle(m.status == "refill" ? Theme.warning : Theme.ink3) }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, Spacing.m).padding(.vertical, 10)
                        }
                    }
                }
                .accessibilityElement(children: .contain)
            }
        }
    }

    @ViewBuilder private func badge(_ status: String) -> some View {
        switch status {
        case "refill": Text("Refill due").font(Theme.font(11, .semibold)).foregroundStyle(Theme.warning).padding(.horizontal, 8).padding(.vertical, 3).background(Theme.warning.opacity(0.15)).clipShape(Capsule())
        case "finished": Text("Finished").font(Theme.font(11, .semibold)).foregroundStyle(Theme.ink3).padding(.horizontal, 8).padding(.vertical, 3).background(Theme.line).clipShape(Capsule())
        default: Text("Current").font(Theme.font(11, .semibold)).foregroundStyle(Theme.green).padding(.horizontal, 8).padding(.vertical, 3).background(Theme.green.opacity(0.15)).clipShape(Capsule())
        }
    }
}
