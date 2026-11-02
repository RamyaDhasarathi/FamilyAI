import SwiftUI

/// Notices that never reached FamilyOS. Say where one actually lived and the household learns which door is missing; a gap is only counted, never
/// read, and produces no dates or tasks. A guardian sees everyone's reports, anyone else their own.
struct IntakeGapsView: View {
    @State private var summary: CaptureSummary?
    @State private var gaps: [IntakeGap] = []
    @State private var loaded = false
    @State private var error: String?
    @State private var reporting = false
    @State private var changed = 0
    private let isSample: Bool

    init() { isSample = false }
    init(summary: CaptureSummary, gaps: [IntakeGap]) { _summary = State(initialValue: summary); _gaps = State(initialValue: gaps); _loaded = State(initialValue: true); isSample = true }

    static func place(_ key: String) -> String {
        ["email": "In an email", "whatsapp_group": "A WhatsApp group", "whatsapp_direct": "A WhatsApp message", "school_portal": "A school portal",
         "school_app": "A school app", "other_app": "Another app", "sms": "A text message", "paper": "On paper", "word_of_mouth": "Word of mouth",
         "unknown": "Not sure"][key] ?? key
    }

    var body: some View {
        List {
            if !loaded && error == nil { LoadingRows(count: 3).listRowBackground(Color.clear).listRowInsets(EdgeInsets()) }
            if let s = summary {
                Section {
                    Text(s.captureRate.map { "About \(Int(($0 * 100).rounded()))% of what arrived was caught" } ?? "Nothing has arrived yet")
                        .font(Theme.font(16, .semibold)).foregroundStyle(Theme.ink)
                    Text("\(s.captured) caught · \(s.missedReported) reported missed").font(Theme.font(13)).foregroundStyle(Theme.ink2)
                    ForEach(s.missedByWhere, id: \.self) { w in
                        VStack(alignment: .leading, spacing: 2) {
                            Text("\(Self.place(w.livedWhere)): \(w.count)").font(Theme.font(14, .medium)).foregroundStyle(Theme.ink)
                            Text(w.means).font(Theme.font(12)).foregroundStyle(Theme.ink3)
                        }
                    }
                } header: { Text("Where things were missed") } footer: { Text(s.caveat) }
            }
            Section("Reported") {
                ForEach(gaps) { g in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(g.title).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                        Text("\(Self.place(g.livedWhere)) · \(Format.day.string(from: g.createdAt))\(g.arrivedAs != nil ? " · arrived later" : "")")
                            .font(Theme.font(12)).foregroundStyle(Theme.ink3)
                    }
                }
                if loaded && gaps.isEmpty && error == nil { Text("Nothing reported missing.").font(Theme.font(13)).foregroundStyle(Theme.ink3) }
                Button { reporting = true } label: { Label("Something did not reach FamilyOS", systemImage: "plus") }
            }
            if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("What did not arrive")
        .navigationBarTitleDisplayMode(.inline)
        .sensoryFeedback(.success, trigger: changed)
        .refreshable { await load() }
        .task { await load() }
        .sheet(isPresented: $reporting) { ReportGapSheet { await load(); changed += 1 } }
    }

    private func load() async {
        guard !isSample else { return }
        do {
            async let s = API.shared.captureSummary(), g = API.shared.intakeGaps()
            (summary, gaps) = try await (s, g)
            error = nil
        } catch { self.error = error.localizedDescription }
        loaded = true
    }
}

private struct ReportGapSheet: View {
    @Environment(\.dismiss) private var dismiss
    let saved: () async -> Void
    @State private var title = ""
    @State private var place = "whatsapp_group"
    @State private var emailed = 0       // 0 not sure, 1 yes, 2 no
    @State private var hadDate = false
    @State private var busy = false
    @State private var error: String?
    private let places = ["email", "whatsapp_group", "whatsapp_direct", "school_portal", "school_app", "other_app", "sms", "paper", "word_of_mouth", "unknown"]

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("What was it about", text: $title)
                    Picker("Where did it live", selection: $place) { ForEach(places, id: \.self) { Text(IntakeGapsView.place($0)).tag($0) } }
                    Picker("Was it also emailed", selection: $emailed) { Text("Not sure").tag(0); Text("Yes").tag(1); Text("No").tag(2) }
                    Toggle("It had a date", isOn: $hadDate)
                } footer: { Text("This is only counted. It makes no task or date, and nothing is read from it.") }
                if let error { Text(error).foregroundStyle(Theme.danger) }
            }
            .navigationTitle("Did not arrive").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("Report") { Task { await save() } }.disabled(busy || title.trimmingCharacters(in: .whitespaces).isEmpty) }
            }
        }
    }

    private func save() async {
        busy = true; defer { busy = false }
        do {
            _ = try await API.shared.reportGap(title: title.trimmingCharacters(in: .whitespaces), livedWhere: place, alsoEmailed: emailed == 0 ? nil : emailed == 1, hadDate: hadDate)
            await saved(); dismiss()
        } catch { self.error = error.localizedDescription }
    }
}
