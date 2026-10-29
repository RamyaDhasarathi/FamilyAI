import SwiftUI

/// What if: someone away between two dates, a purchase, or school reopening on another date. It reads the record and shows what each would touch.
/// It changes nothing and proposes nothing.
struct WhatIfView: View {
    @EnvironmentObject var session: Session
    private enum Kind: String, CaseIterable, Identifiable { case away = "Someone is away", spend = "A purchase", reopen = "School reopens on…"; var id: String { rawValue } }
    @State private var kind: Kind = .away
    @State private var person: UUID?
    @State private var start = Date()
    @State private var end = Calendar.current.date(byAdding: .day, value: 5, to: Date()) ?? Date()
    @State private var amount = ""
    @State private var reopens = Calendar.current.date(byAdding: .day, value: 9, to: Date()) ?? Date()
    @State private var result: ScenarioResult?
    @State private var busy = false
    @State private var error: String?

    private var adults: [Member] { session.members.filter { !$0.isChild } }
    private var ready: Bool { kind == .away ? person != nil : kind == .spend ? (Double(amount) ?? 0) > 0 : true }

    var body: some View {
        List {
            Section {
                Picker("What if", selection: $kind) { ForEach(Kind.allCases) { Text($0.rawValue).tag($0) } }.pickerStyle(.segmented)
                switch kind {
                case .away:
                    Picker("Who", selection: $person) { Text("Choose").tag(UUID?.none); ForEach(adults) { Text($0.displayName).tag(UUID?.some($0.id)) } }
                    DatePicker("From", selection: $start, displayedComponents: .date)
                    DatePicker("To", selection: $end, in: start..., displayedComponents: .date)
                case .spend:
                    TextField("Amount", text: $amount).keyboardType(.decimalPad)
                case .reopen:
                    DatePicker("Reopens on", selection: $reopens, displayedComponents: .date)
                }
                Button { Task { await run() } } label: { Label(busy ? "Looking…" : "Show what it touches", systemImage: "questionmark.circle") }.disabled(busy || !ready)
            } footer: { Text("Nothing is changed or proposed. This only reads what is already recorded.") }
            if let result {
                Section {
                    Text(result.headline).font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                    if result.impacts.isEmpty { Text("Nothing in the record is touched.").font(Theme.font(13)).foregroundStyle(Theme.ink3) }
                    ForEach(Array(result.impacts.enumerated()), id: \.offset) { _, i in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(i.title).font(Theme.font(14)).foregroundStyle(Theme.ink)
                            Text([i.date.map { Format.day.string(from: $0) }, i.note, i.cover.flatMap { $0.isEmpty ? nil : "Could cover: " + $0.joined(separator: ", ") }].compactMap { $0 }.joined(separator: " · "))
                                .font(Theme.font(12)).foregroundStyle(Theme.ink3)
                        }
                    }
                } header: { Text("Result") } footer: { if result.changesNothing { Text("Nothing was changed.") } }
            }
            if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("What if")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func run() async {
        busy = true; defer { busy = false }
        var req: ScenarioRequest
        switch kind {
        case .away: req = ScenarioRequest(kind: .memberAway); req.memberId = person; req.start = start; req.end = end
        case .spend: req = ScenarioRequest(kind: .spend); req.amount = Double(amount)
        case .reopen: req = ScenarioRequest(kind: .schoolReopens); req.reopensOn = reopens
        }
        do { result = try await API.shared.runScenario(req); error = nil } catch { self.error = error.localizedDescription }
    }
}
