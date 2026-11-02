import SwiftUI

/// What the household owes on a rhythm (rent), the accounts it watches for a bill that does not arrive, and the bills now due. FamilyOS makes each
/// month's reminder and never pays: nothing on this screen moves money. Stopping one only ends the reminders.
struct StandingView: View {
    @EnvironmentObject var session: Session
    @State private var standing: [StandingPayment] = []
    @State private var billers: [Biller] = []
    @State private var due: [BillDue] = []
    @State private var loaded = false
    @State private var error: String?
    @State private var addingStanding = false
    @State private var addingBiller = false
    @State private var stopping: StandingPayment?
    @State private var forgetting: Biller?
    @State private var changed = 0
    private let isSample: Bool

    init() { isSample = false }

    /// Rows from data in hand, for previews: nothing is fetched.
    init(standing: [StandingPayment], billers: [Biller], due: [BillDue]) {
        _standing = State(initialValue: standing); _billers = State(initialValue: billers); _due = State(initialValue: due)
        _loaded = State(initialValue: true); isSample = true
    }

    private var canEdit: Bool { session.member?.isChild != true }

    var body: some View {
        List {
            Section {
                Text("Reminders only. FamilyOS makes each month's bill from these and tells you when it is near; you pay it yourself, in the biller's own app or page.")
                    .font(Theme.font(13)).foregroundStyle(Theme.ink3)
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets(top: 0, leading: Spacing.xs, bottom: 0, trailing: Spacing.xs))
            }
            if !loaded && error == nil {
                LoadingRows(count: 3).listRowBackground(Color.clear).listRowInsets(EdgeInsets())
            }
            if !due.isEmpty {
                Section("Due soon") {
                    ForEach(due) { bill in
                        HStack {
                            Text(bill.title).font(Theme.font(15)).foregroundStyle(Theme.ink)
                            Spacer()
                            if let d = bill.dueDate { Text(Format.when(d) ?? "").font(Theme.font(12)).foregroundStyle(Theme.ink3) }
                        }
                    }
                }
            }
            Section {
                ForEach(standing) { item in
                    VStack(alignment: .leading, spacing: 2) {
                        HStack {
                            Text(item.title).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                            Spacer()
                            Text(Format.money(item.amount, item.currency)).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                        }
                        Text("\(item.payee) · day \(item.dayOfMonth) each month · next \(Format.day.string(from: item.nextDue))\(item.visibility == "private" ? " · private" : "")")
                            .font(Theme.font(12)).foregroundStyle(Theme.ink3)
                        if canEdit {
                            Button("Stop reminding", role: .destructive) { stopping = item }.font(Theme.font(13, .medium)).buttonStyle(.borderless)
                        }
                    }
                    .padding(.vertical, 2)
                }
                if loaded && standing.isEmpty && error == nil { Text("Nothing on a rhythm yet.").font(Theme.font(13)).foregroundStyle(Theme.ink3) }
                if canEdit { Button { addingStanding = true } label: { Label("Add a standing payment", systemImage: "plus") } }
            } header: { Text("Standing payments") }
            Section {
                ForEach(billers) { b in
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(b.label) · \(b.provider)").font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                        Text(biller(b)).font(Theme.font(12)).foregroundStyle(Theme.ink3)
                        if canEdit { Button("Stop tracking", role: .destructive) { forgetting = b }.font(Theme.font(13, .medium)).buttonStyle(.borderless) }
                    }
                    .padding(.vertical, 2)
                }
                if loaded && billers.isEmpty && error == nil { Text("No accounts tracked yet.").font(Theme.font(13)).foregroundStyle(Theme.ink3) }
                if canEdit { Button { addingBiller = true } label: { Label("Track an account", systemImage: "plus") } }
            } header: { Text("Accounts watched") } footer: {
                Text("If a bill from one of these does not arrive when it usually does, you are told. The account number is never kept, only the last four digits.")
            }
            if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Bills and standing payments")
        .navigationBarTitleDisplayMode(.inline)
        .sensoryFeedback(.success, trigger: changed)
        .refreshable { await load() }
        .task { await load() }
        .sheet(isPresented: $addingStanding) { AddStandingSheet { await load(); changed += 1 } }
        .sheet(isPresented: $addingBiller) { AddBillerSheet { await load(); changed += 1 } }
        .confirmationDialog("Stop the reminders for this?", isPresented: Binding(get: { stopping != nil }, set: { if !$0 { stopping = nil } }), titleVisibility: .visible, presenting: stopping) { item in
            Button("Stop reminding about \(item.title)", role: .destructive) { Task { await stop(item) } }
        } message: { item in
            Text("\(item.title) to \(item.payee) will no longer be made each month. Nothing is paid or cancelled; you can add it again.")
        }
        .confirmationDialog("Stop tracking this account?", isPresented: Binding(get: { forgetting != nil }, set: { if !$0 { forgetting = nil } }), titleVisibility: .visible, presenting: forgetting) { b in
            Button("Stop tracking \(b.label)", role: .destructive) { Task { await forget(b) } }
        } message: { b in
            Text("You will no longer be told when a \(b.provider) bill is late. The account itself is untouched.")
        }
    }

    private func biller(_ b: Biller) -> String {
        var parts = ["a bill about every \(b.everyDays) days"]
        if let hint = b.identifierHint { parts.append("account ending \(hint)") }
        parts.append(b.lastSeenAt.map { "last seen \(Format.day.string(from: $0))" } ?? "none seen yet")
        if b.visibility == "private" { parts.append("private") }
        return parts.joined(separator: " · ")
    }

    private func load() async {
        guard !isSample else { return }
        do {
            async let s = API.shared.standingPayments(), b = API.shared.billers(), d = API.shared.billsDue()
            (standing, billers, due) = try await (s, b, d)
            error = nil
        } catch { self.error = error.localizedDescription }
        loaded = true
    }

    private func stop(_ item: StandingPayment) async {
        if isSample { standing.removeAll { $0.id == item.id }; return }
        do { try await API.shared.stopStanding(item.id); changed += 1; await load() } catch { self.error = error.localizedDescription }
    }

    private func forget(_ b: Biller) async {
        if isSample { billers.removeAll { $0.id == b.id }; return }
        do { try await API.shared.forgetBiller(b.id); changed += 1; await load() } catch { self.error = error.localizedDescription }
    }
}

private struct AddStandingSheet: View {
    @Environment(\.dismiss) private var dismiss
    let saved: () async -> Void
    @State private var title = ""
    @State private var payee = ""
    @State private var amount = ""
    @State private var day = 1
    @State private var shared = true
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("What it is (Rent)", text: $title)
                    TextField("Who is paid", text: $payee)
                    TextField("Amount", text: $amount).keyboardType(.decimalPad)
                    Picker("Day of the month", selection: $day) { ForEach(1...28, id: \.self) { Text("\($0)").tag($0) } }
                    Toggle("Shared with the household", isOn: $shared)
                } footer: { Text("FamilyOS makes the bill each month and reminds you. It does not pay it.") }
                if let error { Text(error).foregroundStyle(Theme.danger) }
            }
            .navigationTitle("Standing payment").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("Add") { Task { await save() } }.disabled(busy || title.isEmpty || payee.isEmpty || Double(amount) == nil) }
            }
        }
    }

    private func save() async {
        busy = true; defer { busy = false }
        do {
            _ = try await API.shared.addStanding(title: title.trimmingCharacters(in: .whitespaces), payee: payee.trimmingCharacters(in: .whitespaces),
                                                 amount: Double(amount) ?? 0, day: day, shared: shared)
            await saved(); dismiss()
        } catch { self.error = error.localizedDescription }
    }
}

private struct AddBillerSheet: View {
    @Environment(\.dismiss) private var dismiss
    let saved: () async -> Void
    @State private var label = ""
    @State private var provider = ""
    @State private var number = ""
    @State private var every = 30
    @State private var shared = true
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("A name for it (Electricity)", text: $label)
                    TextField("Who bills you", text: $provider)
                    TextField("Account number (optional)", text: $number).keyboardType(.numbersAndPunctuation)
                    Stepper("A bill about every \(every) days", value: $every, in: 7...370, step: 1)
                    Toggle("Shared with the household", isOn: $shared)
                } footer: { Text("The number is turned into a keyed digest and the last four digits; the number itself is not kept.") }
                if let error { Text(error).foregroundStyle(Theme.danger) }
            }
            .navigationTitle("Track an account").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("Add") { Task { await save() } }.disabled(busy || label.isEmpty || provider.isEmpty) }
            }
        }
    }

    private func save() async {
        busy = true; defer { busy = false }
        do {
            let n = number.trimmingCharacters(in: .whitespaces)
            _ = try await API.shared.addBiller(label: label.trimmingCharacters(in: .whitespaces), provider: provider.trimmingCharacters(in: .whitespaces),
                                               number: n.isEmpty ? nil : n, everyDays: every, shared: shared)
            await saved(); dismiss()
        } catch { self.error = error.localizedDescription }
    }
}

#Preview("Bills and standing payments") {
    let id = "44444444-4444-4444-4444-444444444444"
    NavigationStack {
        StandingView(
            standing: PreviewData.decode("""
            [{"id":"\(id)","title":"Rent","payee":"Rao Estates","amount":20000,"currency":"INR","day_of_month":5,"next_due":"\(PreviewData.day(12))","subject_name":null,"visibility":"shared","created_by":"\(PreviewData.amma)"}]
            """),
            billers: PreviewData.decode("""
            [{"id":"\(id)","label":"Electricity","provider":"State Power","identifier_hint":"6789","every_days":30,"grace_days":7,"visibility":"shared","last_seen_at":null}]
            """),
            due: PreviewData.decode("""
            [{"id":"\(id)","title":"Rent, November","due_date":"\(PreviewData.day(12))","status":"accepted"}]
            """))
    }.environmentObject(Session())
}
