import SwiftUI

/// Where each school's notices actually come from: which door brought one first, which only echoed it, and which brought one with no date. Counted
/// from what arrived, never stored. It tells you which door to keep and which is only repeating.
struct RailsView: View {
    @State private var schools: [SchoolRails] = []
    @State private var loaded = false
    @State private var error: String?
    private let isSample: Bool

    init() { isSample = false }
    init(sample: [SchoolRails]) { _schools = State(initialValue: sample); _loaded = State(initialValue: true); isSample = true }

    var body: some View {
        List {
            if !loaded && error == nil { LoadingRows(count: 3).listRowBackground(Color.clear).listRowInsets(EdgeInsets()) }
            else if loaded && schools.isEmpty && error == nil {
                EmptyState(symbol: "arrow.triangle.branch", title: "No schools yet", text: "Once a school's notices arrive, you see which door each came through.", action: nil)
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets())
            }
            ForEach(schools) { s in
                Section {
                    if let said = s.said { Text(said).font(Theme.font(14)).foregroundStyle(Theme.ink2) }
                    else { Text("No notice from this school has arrived yet.").font(Theme.font(13)).foregroundStyle(Theme.ink3) }
                    ForEach(s.rails) { r in
                        HStack {
                            Text(r.label).font(Theme.font(15)).foregroundStyle(Theme.ink)
                            Spacer()
                            Text("\(r.first) first · \(r.echo) echoed · \(r.empty) no date").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                        }
                    }
                } header: { Text("\(s.school) · \(s.notices) notice\(s.notices == 1 ? "" : "s")") }
            }
            if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("How notices arrive")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        guard !isSample else { return }
        do { schools = try await API.shared.rails(); error = nil } catch { self.error = error.localizedDescription }
        loaded = true
    }
}
