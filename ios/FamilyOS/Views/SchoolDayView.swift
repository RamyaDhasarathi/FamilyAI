import SwiftUI

/// The school copilot: what each child needs tomorrow, the forms still to come back, and a draft note when a child will be away. Read from the
/// notices; nothing is guessed and nothing is sent.
struct SchoolDayView: View {
    @EnvironmentObject var session: Session
    enum Tab: String, CaseIterable, Identifiable { case tomorrow = "Tomorrow", forms = "Forms", absence = "Absence"; var id: String { rawValue } }
    @State private var tab: Tab = .tomorrow
    @State private var day: SchoolDay?
    @State private var forms: [SchoolForm]?
    @State private var error: String?

    var body: some View {
        List {
            Section {
                Picker("Show", selection: $tab) { ForEach(Tab.allCases) { Text($0.rawValue).tag($0) } }.pickerStyle(.segmented)
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets())
            }
            switch tab {
            case .tomorrow: tomorrow
            case .forms: formsList
            case .absence: AbsenceNote(children: session.members.filter(\.isChild))
            }
            if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("School")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task { await load() }
    }

    @ViewBuilder private var tomorrow: some View {
        if let day {
            if day.nothing {
                EmptyState(symbol: "backpack", title: "Nothing dated for \(Format.long.string(from: day.date))",
                           text: "No notice names anything for the children that day.", action: nil)
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets())
            }
            ForEach(day.children) { kid in
                Section {
                    ForEach(kid.items, id: \.self) { item in
                        let row = VStack(alignment: .leading, spacing: 2) {
                            Text(item.title).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                            Text([item.kind.capitalized, item.time.map(Format.clockText), item.undecided ? "not yet accepted" : nil, item.returned ? "done" : nil]
                                .compactMap { $0 }.joined(separator: " · ")).font(Theme.font(12)).foregroundStyle(Theme.ink3)
                        }
                        if let id = item.artifactId { NavigationLink { NoticeView(artifactId: id, title: item.title) } label: { row } } else { row }
                    }
                    if !kid.bring.isEmpty {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Bring or wear").font(Theme.font(12, .semibold)).foregroundStyle(Theme.ink3)
                            ForEach(kid.bring, id: \.self) { Text("• " + $0).font(Theme.font(14)).foregroundStyle(Theme.ink2) }
                        }
                    }
                } header: { Text([kid.child, kid.class].compactMap { $0 }.joined(separator: " · ")) }
            }
        } else if error == nil { LoadingRows(count: 3).listRowBackground(Color.clear).listRowInsets(EdgeInsets()) }
    }

    @ViewBuilder private var formsList: some View {
        if let forms {
            if forms.isEmpty {
                EmptyState(symbol: "doc.text", title: "No forms waiting", text: "Slips and forms that need to come back show here.", action: nil)
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets())
            }
            ForEach(["to return", "undecided", "returned"], id: \.self) { state in
                let group = forms.filter { $0.state == state }
                if !group.isEmpty {
                    Section(state == "undecided" ? "Not yet accepted" : state.capitalized) {
                        ForEach(group) { f in
                            NavigationLink { NoticeView(artifactId: f.artifactId, title: f.title) } label: {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(f.title).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                                    Text([f.child, (f.late ? "was due " : "by ") + Format.day.string(from: f.dueDate)].compactMap { $0 }.joined(separator: " · "))
                                        .font(Theme.font(12)).foregroundStyle(f.late ? Theme.danger : Theme.ink3)
                                }
                            }
                        }
                    }
                }
            }
        } else if error == nil { LoadingRows(count: 3).listRowBackground(Color.clear).listRowInsets(EdgeInsets()) }
    }

    private func load() async {
        do {
            day = try await API.shared.schoolTomorrow()
            forms = try await API.shared.schoolForms()
            error = nil
        } catch { self.error = error.localizedDescription }
    }
}

/// A draft note for the teacher, from a fixed template. Edit it and send it yourself: FamilyOS does not send it.
private struct AbsenceNote: View {
    let children: [Member]
    @State private var child: UUID?
    @State private var on = Date()
    @State private var several = false
    @State private var until = Date()
    @State private var reason = ""
    @State private var draft: AbsenceDraft?
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        Section {
            if children.isEmpty {
                Text("Add a child in the household first.").font(Theme.font(13)).foregroundStyle(Theme.ink3)
            } else {
                Picker("Child", selection: $child) { ForEach(children) { Text($0.displayName).tag(Optional($0.id)) } }
                DatePicker("From", selection: $on, displayedComponents: .date)
                Toggle("More than one day", isOn: $several)
                if several { DatePicker("Until", selection: $until, in: on..., displayedComponents: .date) }
                TextField("Reason (optional)", text: $reason)
                Button(busy ? "…" : "Write the note") { Task { await write() } }.disabled(busy || (child ?? children.first?.id) == nil)
            }
        } header: { Text("Absence note") } footer: { Text("A draft from a fixed template. Edit it and send it yourself; FamilyOS does not send it.") }
        if let draft {
            Section("Draft") {
                Text(draft.subject).font(Theme.font(14, .semibold))
                Text(draft.body).font(Theme.font(14)).textSelection(.enabled)
                ShareLink(item: draft.subject + "\n\n" + draft.body) { Label("Send or copy", systemImage: "square.and.arrow.up") }
            }
        }
        if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger) }
    }

    private func write() async {
        guard let id = child ?? children.first?.id else { return }
        busy = true; defer { busy = false }
        do { draft = try await API.shared.absenceNote(child: id, on: on, until: several ? until : nil, reason: reason.isEmpty ? nil : reason); error = nil }
        catch { self.error = error.localizedDescription }
    }
}
