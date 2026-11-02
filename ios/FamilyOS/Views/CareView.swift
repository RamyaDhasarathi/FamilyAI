import SwiftUI

/// One person's papers, bills, appointments, medicines and anything that looked like a scam, in one place: the view for looking after a parent. Read
/// through your own visibility, so you see what you are allowed to see about them and no more.
struct CareListView: View {
    @EnvironmentObject var session: Session

    var body: some View {
        List {
            Section {
                Text("Pick a person to see what is coming up for them: documents that are expiring, bills, appointments, medicines and messages that looked wrong.")
                    .font(Theme.font(13)).foregroundStyle(Theme.ink3)
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets(top: 0, leading: Spacing.xs, bottom: 0, trailing: Spacing.xs))
            }
            Section {
                ForEach(session.members) { m in
                    NavigationLink { CareDetailView(member: m) } label: {
                        HStack(spacing: Spacing.m) {
                            Avatar(member: m, size: 32)
                            VStack(alignment: .leading, spacing: 0) {
                                Text(m.displayName).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                                Text(m.role.capitalized).font(Theme.font(12)).foregroundStyle(Theme.ink3)
                            }
                        }
                    }
                }
            }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Looking after someone")
        .navigationBarTitleDisplayMode(.inline)
    }
}

struct CareDetailView: View {
    let member: Member
    @State private var care: CareSummary?
    @State private var error: String?
    private let sample: CareSummary?

    init(member: Member) { self.member = member; sample = nil }
    init(member: Member, sample: CareSummary) { self.member = member; self.sample = sample; _care = State(initialValue: sample) }

    var body: some View {
        List {
            if care == nil && error == nil { LoadingRows(count: 4).listRowBackground(Color.clear).listRowInsets(EdgeInsets()) }
            if let care {
                if care.documents.isEmpty && care.documentChecks.isEmpty && care.bills.isEmpty && care.appointments.isEmpty && care.medications.isEmpty
                    && care.standing.isEmpty && care.unusual.isEmpty && care.scams.isEmpty && care.handedOver.isEmpty {
                    EmptyState(symbol: "heart.text.square", title: "Nothing to show", text: "Nothing about \(member.displayName) that you are allowed to see has come up.", action: nil)
                        .listRowBackground(Color.clear).listRowInsets(EdgeInsets())
                }
                if !care.documentChecks.isEmpty {
                    Section("Needs a look") { ForEach(Array(care.documentChecks.enumerated()), id: \.offset) { _, c in note(c) } }
                }
                if !care.scams.isEmpty {
                    Section("Messages that looked wrong") {
                        ForEach(Array(care.scams.enumerated()), id: \.offset) { _, s in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(s.headline ?? "A message").font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                                Text("\(Format.stamp.string(from: s.receivedAt))\(s.suspicion?.level.map { " · \($0) reading" } ?? "")").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                            }
                        }
                    }
                }
                if !care.appointments.isEmpty { Section("Appointments") { ForEach(Array(care.appointments.enumerated()), id: \.offset) { _, a in dated(a) } } }
                if !care.bills.isEmpty { Section("Bills") { ForEach(Array(care.bills.enumerated()), id: \.offset) { _, b in dated(b) } } }
                if !care.standing.isEmpty {
                    Section("Regular payments") {
                        ForEach(care.standing) { s in
                            HStack { Text(s.title).font(Theme.font(15)); Spacer(); Text(Format.money(s.amount, s.currency)).font(Theme.font(14)).foregroundStyle(Theme.ink2) }
                        }
                    }
                }
                if !care.medications.isEmpty {
                    Section("Medicines") {
                        ForEach(Array(care.medications.enumerated()), id: \.offset) { _, m in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(m.drug).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                                Text([m.doseText, m.timesPerDay.map { "\($0) a day" }, m.status.capitalized, m.daysLeft.map { "\($0) days left" }].compactMap { $0 }.joined(separator: " · "))
                                    .font(Theme.font(12)).foregroundStyle(Theme.ink3)
                            }
                        }
                    }
                }
                if !care.documents.isEmpty {
                    Section("Documents") {
                        ForEach(Array(care.documents.enumerated()), id: \.offset) { _, d in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(d.label).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                                Text([d.expiresOn.map { "expires \(Format.dayYear.string(from: $0))" }, d.status.capitalized].compactMap { $0 }.joined(separator: " · "))
                                    .font(Theme.font(12)).foregroundStyle(d.status == "expired" ? Theme.danger : Theme.ink3)
                            }
                        }
                    }
                }
                if !care.unusual.isEmpty { Section("Unusual charges") { ForEach(Array(care.unusual.enumerated()), id: \.offset) { _, u in note(u) } } }
                if !care.handedOver.isEmpty {
                    Section("Handed to someone else") {
                        ForEach(care.handedOver) { g in
                            VStack(alignment: .leading, spacing: 2) {
                                Text("\(g.granteeName): \(g.reason)").font(Theme.font(14)).foregroundStyle(Theme.ink)
                                Text("until \(Format.dayYear.string(from: g.expiresAt))").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                            }
                        }
                    }
                }
            }
            if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle(member.displayName)
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task { await load() }
    }

    private func note(_ n: CareNote) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(n.title).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
            if let why = n.why { Text(why).font(Theme.font(12)).foregroundStyle(Theme.ink3) }
        }
    }

    private func dated(_ d: CareDated) -> some View {
        HStack {
            Text(d.title).font(Theme.font(15)).foregroundStyle(Theme.ink)
            Spacer()
            if let due = d.dueDate { Text(Format.when(due) ?? "").font(Theme.font(12)).foregroundStyle(Theme.ink3) }
        }
    }

    private func load() async {
        guard sample == nil else { return }
        do { care = try await API.shared.care(member.id); error = nil } catch { self.error = error.localizedDescription }
    }
}
