import SwiftUI

/// The emergency card, and "I'm safe" / "I need help". A guardian can share the card by a link that expires; it is shown once and can be revoked.
struct EmergencyView: View {
    @EnvironmentObject var session: Session
    @State private var card: EmergencyCard?
    @State private var checkins: [EmergencyCheckin] = []
    @State private var shares: [EmergencyShare] = []
    @State private var error: String?
    @State private var notice: String?
    @State private var sharing = false
    @State private var madeLink: URL?
    @State private var confirmHelp = false
    @State private var sent = 0

    private var isGuardian: Bool { session.member?.role == "guardian" }

    var body: some View {
        List {
            Section("Check in") {
                HStack {
                    Button { Task { await checkin(safe: true) } } label: { Label("I'm safe", systemImage: "checkmark.circle").frame(maxWidth: .infinity) }
                        .buttonStyle(.borderedProminent).tint(Theme.success)
                    Button { confirmHelp = true } label: { Label("I need help", systemImage: "exclamationmark.triangle").frame(maxWidth: .infinity) }
                        .buttonStyle(.bordered).tint(Theme.danger)
                }
                .font(Theme.font(14, .semibold)).listRowSeparator(.hidden)
                ForEach(checkins) { c in
                    HStack {
                        Text(c.name).font(Theme.font(14, .medium))
                        Spacer()
                        Text((c.status == "safe" ? "safe" : "needs help") + " · " + Format.stamp.string(from: c.at)).font(Theme.font(12))
                            .foregroundStyle(c.status == "safe" ? Theme.ink3 : Theme.danger)
                    }
                    .accessibilityElement(children: .combine)
                }
            }
            if let card {
                Section("Contacts") {
                    if card.contacts.isEmpty { Text("None added. A guardian adds them in the console.").font(Theme.font(13)).foregroundStyle(Theme.ink3) }
                    ForEach(card.contacts, id: \.self) { c in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(c.name).font(Theme.font(15, .medium))
                            let rest = [c.relation, c.phone].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · ")
                            if !rest.isEmpty { Text(rest).font(Theme.font(12)).foregroundStyle(Theme.ink3) }
                        }
                    }
                }
                if !card.pickup.isEmpty {
                    Section("Who may collect a child") {
                        ForEach(card.pickup, id: \.self) { p in
                            Text("\(p.child): \(p.name)" + ([p.relation, p.phone].compactMap { $0 }.filter { !$0.isEmpty }.map { " · " + $0 }.joined()))
                                .font(Theme.font(14))
                        }
                    }
                }
                Section("People") {
                    ForEach(card.people, id: \.self) { person in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(person.name).font(Theme.font(15, .medium))
                            let bits = [person.bloodGroup.map { "blood group \($0)" }, person.allergies.map { "allergies: \($0)" }].compactMap { $0 }
                            if !bits.isEmpty { Text(bits.joined(separator: " · ")).font(Theme.font(12)).foregroundStyle(Theme.ink2) }
                            if !person.medicines.isEmpty { Text("Takes: " + person.medicines.joined(separator: "; ")).font(Theme.font(12)).foregroundStyle(Theme.ink2) }
                        }
                    }
                }
                if !card.documents.isEmpty {
                    Section("Documents") {
                        ForEach(card.documents, id: \.self) { d in
                            VStack(alignment: .leading, spacing: 2) {
                                Text("\(d.kind.capitalized)" + (d.holder.map { " · \($0)" } ?? "")).font(Theme.font(14, .medium))
                                let bits = [d.issuer, d.identifierTail.map { "…\($0)" }, d.expiresOn.map { "expires " + Format.dayYear.string(from: $0) }].compactMap { $0 }
                                if !bits.isEmpty { Text(bits.joined(separator: " · ")).font(Theme.font(12)).foregroundStyle(Theme.ink3) }
                            }
                        }
                    }
                }
                if let access = card.homeAccess, !access.isEmpty { Section("Getting into the home") { Text(access).font(Theme.font(14)) } }
            } else if error == nil {
                LoadingRows(count: 4).listRowBackground(Color.clear).listRowInsets(EdgeInsets())
            }
            if isGuardian { shareSection }
            if let notice { Text(notice).font(Theme.font(13)).foregroundStyle(Theme.ink2).listRowBackground(Color.clear) }
            if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Emergency card")
        .navigationBarTitleDisplayMode(.inline)
        .sensoryFeedback(.success, trigger: sent)
        .confirmationDialog("Tell the guardians you need help?", isPresented: $confirmHelp, titleVisibility: .visible) {
            Button("Yes, I need help", role: .destructive) { Task { await checkin(safe: false) } }
            Button("Cancel", role: .cancel) {}
        } message: { Text("They are told at once and asked to call you.") }
        .sheet(isPresented: $sharing) { ShareCardSheet { label, hours, home in await make(label, hours, home) } }
        .refreshable { await load() }
        .task { await load() }
    }

    @ViewBuilder private var shareSection: some View {
        Section {
            Button { sharing = true } label: { Label("Share the card by a link", systemImage: "link") }
            if let madeLink {
                ShareLink(item: madeLink) { Label("Send the link you just made (shown once)", systemImage: "square.and.arrow.up") }
            }
            ForEach(shares.filter { $0.active == true }) { s in
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(s.label).font(Theme.font(14, .medium))
                        Text("until \(Format.stamp.string(from: s.expiresAt)) · opened \(s.openedCount ?? 0)×" + (s.includeHome ? " · with home access" : ""))
                            .font(Theme.font(12)).foregroundStyle(Theme.ink3)
                    }
                    Spacer()
                    Button("Revoke", role: .destructive) { Task { await revoke(s) } }.font(Theme.font(13, .semibold)).buttonStyle(.borderless)
                }
            }
        } header: { Text("Shared links") } footer: {
            Text("Anyone with a link sees the card until it expires or you revoke it. Home access is included only if you tick it.")
        }
    }

    private func load() async {
        do {
            card = try await API.shared.emergencyCard()
            checkins = (try? await API.shared.emergencyCheckins()) ?? []
            if isGuardian { shares = (try? await API.shared.emergencyShares()) ?? [] }
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    private func checkin(safe: Bool) async {
        do {
            try await API.shared.emergencyCheckin(safe: safe)
            sent += 1; notice = safe ? "Noted: you are safe." : "The guardians have been told."
            checkins = (try? await API.shared.emergencyCheckins()) ?? checkins
        } catch { self.error = error.localizedDescription }
    }

    private func make(_ label: String, _ hours: Int, _ home: Bool) async {
        do {
            let made = try await API.shared.shareEmergency(label: label, hours: hours, includeHome: home)
            if let base = Server.baseURL { madeLink = URL(string: made.path, relativeTo: base)?.absoluteURL }
            shares = (try? await API.shared.emergencyShares()) ?? shares
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    private func revoke(_ s: EmergencyShare) async {
        do { try await API.shared.revokeEmergencyShare(s.id); madeLink = nil; shares = (try? await API.shared.emergencyShares()) ?? [] } catch { self.error = error.localizedDescription }
    }
}

private struct ShareCardSheet: View {
    let make: (String, Int, Bool) async -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var label = ""
    @State private var hours = 24
    @State private var home = false
    @State private var busy = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Who is it for?") { TextField("The sitter, the school office…", text: $label) }
                Section("How long") { Stepper("\(hours) hour\(hours == 1 ? "" : "s")", value: $hours, in: 1...72) }
                Section { Toggle("Include how to get into the home", isOn: $home) } footer: { Text("Off unless this person needs to get in.") }
            }
            .navigationTitle("Share the card")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(busy ? "…" : "Make link") { Task { busy = true; await make(label, hours, home); dismiss() } }
                        .disabled(label.trimmingCharacters(in: .whitespaces).isEmpty || busy)
                }
            }
        }
    }
}
