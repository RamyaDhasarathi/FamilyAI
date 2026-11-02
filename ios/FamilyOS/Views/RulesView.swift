import SwiftUI

/// What is always true, the rules the household set, and who sees what. A guardian flips the switches; everyone else reads them. Nothing here
/// undoes what was already done: a change applies from now on, and is written to the activity record.
struct RulesView: View {
    @EnvironmentObject var session: Session
    @State private var c: Constitution?
    @State private var error: String?
    @State private var changed = 0
    @State private var saving: String?

    private var isGuardian: Bool { session.member?.role == "guardian" }

    var body: some View {
        List {
            if let c {
                Section("Always true") {
                    ForEach(c.walls, id: \.self) { Text($0).font(Theme.font(14)).foregroundStyle(Theme.ink2) }
                }
                Section {
                    ForEach(c.rules) { rule in ruleRow(rule) }
                } header: { Text("Rules") } footer: {
                    Text(isGuardian ? "A change applies from now on; nothing already done is undone. Every change is written to Activity."
                                    : "Only a guardian can change these.")
                }
                Section {
                    ForEach(c.people) { person in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(person.displayName).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                            Text([person.role.capitalized, person.circleWords].compactMap { $0 }.joined(separator: " · "))
                                .font(Theme.font(12)).foregroundStyle(Theme.ink3)
                            ForEach(person.sees, id: \.self) { Text("• " + $0).font(Theme.font(13)).foregroundStyle(Theme.ink2) }
                        }
                        .accessibilityElement(children: .combine)
                    }
                } header: { Text("Who sees what") }
            } else if error == nil {
                LoadingRows(count: 5).listRowBackground(Color.clear).listRowInsets(EdgeInsets())
            }
            if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Rules and access")
        .navigationBarTitleDisplayMode(.inline)
        .sensoryFeedback(.success, trigger: changed)
        .refreshable { await load() }
        .task { await load() }
    }

    @ViewBuilder private func ruleRow(_ rule: HouseholdRule) -> some View {
        if rule.isSwitch {
            VStack(alignment: .leading, spacing: 4) {
                Toggle(isOn: Binding(get: { rule.on }, set: { on in Task { await set(rule, on) } })) {
                    Text(rule.title).font(Theme.font(15, .medium))
                }
                .disabled(!isGuardian || rule.fixed || saving != nil)
                Text(rule.sentence).font(Theme.font(12)).foregroundStyle(Theme.ink3)
                if let why = rule.whyFixed, rule.fixed { Text(why).font(Theme.font(12)).foregroundStyle(Theme.ink3) }
            }
        } else {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(rule.title).font(Theme.font(15, .medium))
                    Spacer()
                    Text(value(rule)).font(Theme.font(14)).foregroundStyle(Theme.ink2)
                }
                Text(rule.sentence).font(Theme.font(12)).foregroundStyle(Theme.ink3)
                if isGuardian { Text("Change this in the console.").font(Theme.font(12)).foregroundStyle(Theme.ink3) }
            }
            .accessibilityElement(children: .combine)
        }
    }

    private func value(_ rule: HouseholdRule) -> String {
        switch rule.kind {
        case "number": return rule.value.map { "\($0) \(rule.unit ?? "")" } ?? ""
        case "who": return rule.options?.first { $0.id == rule.memberId }?.name ?? "Nobody"
        default: return rule.text ?? "Not set"
        }
    }

    private func set(_ rule: HouseholdRule, _ on: Bool) async {
        saving = rule.key; defer { saving = nil }
        do { try await API.shared.setRule(rule.key, on); changed += 1; error = nil; await load() } catch { self.error = error.localizedDescription }
    }

    private func load() async {
        do { c = try await API.shared.constitution(); error = nil } catch { self.error = error.localizedDescription }
    }
}
