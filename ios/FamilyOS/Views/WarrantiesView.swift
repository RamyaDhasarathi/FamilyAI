import SwiftUI

/// Returns and warranties: what was bought, until when it can go back, until
/// when it is covered, and how many days are left of each. Add one by hand;
/// swipe one away once it is returned, claimed or not worth watching.
struct WarrantiesView: View {
    @State private var items: [Warranty] = []
    @State private var loaded = false
    @State private var error: String?
    @State private var adding = false
    @State private var closed = 0
    private let isSample: Bool

    init() { isSample = false }

    /// A list from data in hand, for previews: nothing is fetched.
    init(sample: [Warranty]) {
        _items = State(initialValue: sample)
        _loaded = State(initialValue: true)
        isSample = true
    }

    var body: some View {
        List {
            Section {
                Text("FamilyOS tells you before a return window or a warranty ends. Swipe one away once it is returned or claimed.")
                    .font(Theme.font(13)).foregroundStyle(Theme.ink3)
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets(top: 0, leading: Spacing.xs, bottom: 0, trailing: Spacing.xs))
            }
            if !loaded && error == nil {
                LoadingRows(count: 3).listRowBackground(Color.clear).listRowInsets(EdgeInsets())
            } else if loaded && items.isEmpty && error == nil {
                EmptyState(symbol: "checkmark.shield", title: "Nothing is being watched",
                           text: "Add a purchase with how long it can go back and how long it is covered.",
                           action: (label: "Add a purchase", run: { adding = true }))
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets())
            }
            if !items.isEmpty {
                Section {
                    ForEach(items) { w in
                        row(w)
                            .swipeActions {
                                Button { Task { await close(w) } } label: { Label("Done with it", systemImage: "checkmark") }.tint(Theme.success)
                            }
                    }
                }
            }
            if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Returns and warranties")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { adding = true } label: { Image(systemName: "plus") }.accessibilityLabel("Add a purchase")
            }
        }
        .sheet(isPresented: $adding) { AddWarrantyView { await load() } }
        .sensoryFeedback(.success, trigger: closed)
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        guard !isSample else { return }
        do { items = try await API.shared.warranties(); error = nil } catch { self.error = error.localizedDescription }
        loaded = true
    }

    private func close(_ w: Warranty) async {
        if isSample { items.removeAll { $0.id == w.id }; return }
        do { try await API.shared.closeWarranty(w.id); closed += 1; await load() } catch { self.error = error.localizedDescription }
    }

    @ViewBuilder private func row(_ w: Warranty) -> some View {
        let content = VStack(alignment: .leading, spacing: Spacing.xs) {
            Text(w.title).font(Theme.font(16, .medium)).foregroundStyle(Theme.ink)
            let bought = [w.merchant, w.purchasedOn.map { "bought " + Format.dayYear.string(from: $0) }].compactMap { $0 }
            if !bought.isEmpty { Text(bought.joined(separator: " · ")).font(Theme.font(12)).foregroundStyle(Theme.ink3) }
            if let d = w.returnBy { deadline("Return by", d, soon: 3) }
            if let d = w.warrantyUntil { deadline("Warranty to", d, soon: 30) }
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
        if let id = w.artifactId {
            NavigationLink { NoticeView(artifactId: id, title: w.title) } label: { content }
                .accessibilityHint("Opens the invoice")
        } else {
            content
        }
    }

    /// A date with what is left of it: amber when it is close, red once it has passed.
    private func deadline(_ what: String, _ date: Date, soon: Int) -> some View {
        let left = Self.daysLeft(date)
        let tint = left < 0 ? Theme.danger : left <= soon ? Theme.warning : Theme.ink2
        let note = left < 0 ? "ended" : left == 0 ? "today" : left == 1 ? "1 day left" : "\(left) days left"
        return HStack(spacing: Spacing.s) {
            Text("\(what) \(Format.dayYear.string(from: date))").font(Theme.font(13)).foregroundStyle(Theme.ink2)
            Spacer(minLength: Spacing.s)
            Tag(text: note, tint: tint)
        }
    }

    static func daysLeft(_ date: Date, from now: Date = Date()) -> Int {
        let cal = Calendar.current
        return cal.dateComponents([.day], from: cal.startOfDay(for: now), to: cal.startOfDay(for: date)).day ?? 0
    }
}

/// The form: what, where, when, and how long each window runs. The server works out the dates.
struct AddWarrantyView: View {
    let saved: () async -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var title = ""
    @State private var merchant = ""
    @State private var purchased = Date()
    @State private var canReturn = true
    @State private var returnDays = 7
    @State private var hasWarranty = true
    @State private var warrantyMonths = 12
    @State private var saving = false
    @State private var error: String?

    private var ready: Bool { !title.trimmingCharacters(in: .whitespaces).isEmpty && (canReturn || hasWarranty) && !saving }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("What was bought", text: $title).textInputAutocapitalization(.sentences)
                    TextField("Where (optional)", text: $merchant).textInputAutocapitalization(.words)
                    DatePicker("Bought on", selection: $purchased, in: ...Date(), displayedComponents: .date)
                }
                Section {
                    Toggle("Can be returned", isOn: $canReturn.animation())
                    if canReturn {
                        Stepper(value: $returnDays, in: 1...365) { Text("\(returnDays) day\(returnDays == 1 ? "" : "s") to return it") }
                    }
                    Toggle("Has a warranty", isOn: $hasWarranty.animation())
                    if hasWarranty {
                        Stepper(value: $warrantyMonths, in: 1...120) { Text(months(warrantyMonths) + " of warranty") }
                    }
                } footer: {
                    Text("Check the start date on the invoice: an extended warranty can begin after the maker's own.")
                }
                if let error { Section { Text(error).foregroundStyle(Theme.danger) } }
            }
            .scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
            .navigationTitle("Add a purchase").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { Task { await save() } }.disabled(!ready).fontWeight(.semibold)
                }
            }
        }
    }

    private func months(_ n: Int) -> String {
        n % 12 == 0 ? "\(n / 12) year\(n == 12 ? "" : "s")" : "\(n) month\(n == 1 ? "" : "s")"
    }

    private func save() async {
        saving = true
        defer { saving = false }
        let shop = merchant.trimmingCharacters(in: .whitespaces)
        do {
            _ = try await API.shared.addWarranty(title: title.trimmingCharacters(in: .whitespaces), merchant: shop.isEmpty ? nil : shop, purchasedOn: purchased,
                                                 returnDays: canReturn ? returnDays : nil, warrantyMonths: hasWarranty ? warrantyMonths : nil)
            await saved()
            dismiss()
        } catch { self.error = error.localizedDescription }
    }
}

extension PreviewData {
    static let warranties: [Warranty] = decode("""
    [
      {"id":"99999999-0000-0000-0000-000000000002","title":"Bose QuietComfort headphones","merchant":"Amazon","purchased_on":"\(day(-5))","return_by":"\(day(2))","warranty_until":"\(day(360))","artifact_id":null},
      {"id":"99999999-0000-0000-0000-000000000001","title":"Samsung refrigerator","merchant":"Croma","purchased_on":"\(day(-345))","return_by":null,"warranty_until":"\(day(20))","artifact_id":"aaaaaaaa-0000-0000-0000-000000000009"},
      {"id":"99999999-0000-0000-0000-000000000003","title":"Mixer grinder","merchant":null,"purchased_on":"\(day(-400))","return_by":null,"warranty_until":"\(day(330))","artifact_id":null}
    ]
    """)
}

#Preview("Returns and warranties") {
    NavigationStack { WarrantiesView(sample: PreviewData.warranties) }
}

#Preview("Returns and warranties · dark, large text") {
    NavigationStack { WarrantiesView(sample: PreviewData.warranties) }.preferredColorScheme(.dark).dynamicTypeSize(.xxxLarge)
}

#Preview("Add a purchase") { AddWarrantyView { } }
