import SwiftUI

/// Settings: who is signed in, the household, what is connected, how
/// reminders reach you, what this phone keeps, and the way out. Grouped
/// the way the system groups its own settings. What the console still owns
/// is said plainly rather than hidden.
struct SettingsView: View {
    @EnvironmentObject var session: Session
    @State private var household: Household?
    @State private var devices: [Device] = []
    @State private var error: String?
    @State private var confirmSignOut = false
    @State private var copied = false

    var body: some View {
        List {
            if let m = session.member {
                Section {
                    HStack(spacing: Spacing.l) {
                        Avatar(member: m, size: 64)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(m.displayName).font(Theme.font(20, .semibold)).foregroundStyle(Theme.ink)
                            Text(m.role.capitalized + (household.map { " · \($0.name)" } ?? "")).font(Theme.font(13)).foregroundStyle(Theme.ink3)
                            if let e = m.email { Text(e).font(Theme.font(12)).foregroundStyle(Theme.ink3) }
                        }
                    }
                    .padding(.vertical, Spacing.xs)
                    .accessibilityElement(children: .combine)
                }
            }
            if let error { Section { ErrorState(text: error) { Task { await load() } } }.listRowInsets(EdgeInsets()).listRowBackground(Color.clear) }
            if session.outboxLeft > 0 {
                Section { OfflineBanner() }.listRowInsets(EdgeInsets()).listRowBackground(Color.clear)
            }

            Section("Household") {
                row("house", "Household", household?.name ?? "—")
                row("person.2", "Members", "\(session.members.count)")
                row("globe", "Lives in", [household?.country, household?.timezone, household?.currency].compactMap { $0 }.joined(separator: " · "))
                Text("Members, roles, schools and the standing rules are managed on the console today.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
            }

            Section {
                if let addr = household?.inboundAddress {
                    Button { UIPasteboard.general.string = addr; copied = true } label: {
                        HStack(spacing: Spacing.m) {
                            Image(systemName: "envelope").foregroundStyle(Theme.ink2).frame(width: 24)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Mail notices to").foregroundStyle(Theme.ink)
                                Text(addr).font(Theme.font(12)).foregroundStyle(Theme.ink3).lineLimit(1).truncationMode(.middle)
                            }
                            Spacer()
                            Image(systemName: copied ? "checkmark" : "doc.on.doc").foregroundStyle(Theme.primary)
                        }
                    }
                    .accessibilityLabel("Copy the mail-in address")
                }
                if let bot = household?.telegramBot {
                    row("paperplane", "Telegram", (session.member?.telegramLinked ?? false) ? "Linked · @\(bot)" : "Not linked · @\(bot)")
                    Button((session.member?.telegramLinked ?? false) ? "Link another device" : "Link my Telegram") { Task { await linkTelegram() } }.foregroundStyle(Theme.primary)
                    Text("Opens Telegram on this phone; press Start and the bot says who it linked. Then reminders and questions can go that way too.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                }
                row("tray.and.arrow.down", "Gmail", "Managed on the console")
                NavigationLink { DevicesView(devices: devices, reload: { await load() }) } label: {
                    HStack(spacing: Spacing.m) {
                        Image(systemName: "iphone").foregroundStyle(Theme.ink2).frame(width: 24)
                        Text("Phones and shortcuts").foregroundStyle(Theme.ink)
                        Spacer()
                        Text("\(devices.count)").foregroundStyle(Theme.ink3)
                    }
                }
            } header: { Text("Connected") } footer: { Text("Each connection sends notices in; none of them lets FamilyOS send on your behalf without a tap.") }

            Section {
                row("bell", "Reminders", "By mail" + ((session.member?.telegramLinked ?? false) ? " and Telegram" : ""))
                Text("Push notifications are not built yet; reminders reach you the way the household chose on the console. The day's brief is on Today.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
            } header: { Text("Notifications") }

            Section {
                VStack(alignment: .leading, spacing: Spacing.s) {
                    Label("Private by default", systemImage: "lock").font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                    Text("What you share is yours alone unless you share it with the household. A child's notices follow the consent their guardians set.").font(Theme.font(13)).foregroundStyle(Theme.ink2)
                }.padding(.vertical, Spacing.xs)
                VStack(alignment: .leading, spacing: Spacing.s) {
                    Label("What this phone keeps", systemImage: "iphone").font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                    Text("Your sign-in, in the Keychain. Anything done with no signal, until it is sent. No notice text, no pictures.").font(Theme.font(13)).foregroundStyle(Theme.ink2)
                }.padding(.vertical, Spacing.xs)
                VStack(alignment: .leading, spacing: Spacing.s) {
                    Label("What FamilyOS never does", systemImage: "nosign").font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                    Text("Hold a card, a password or a bank login. Pay. Act without showing you exactly what first.").font(Theme.font(13)).foregroundStyle(Theme.ink2)
                }.padding(.vertical, Spacing.xs)
            } header: { Text("Privacy") }

            Section {
                if Server.deviceToken != nil {
                    Text("The share sheet sends with its own token, listed under Phones and shortcuts as “iPhone app”. Revoking it there stops the share sheet, not the app.").font(Theme.font(13)).foregroundStyle(Theme.ink2)
                } else {
                    Button("Issue a token for the share sheet") { Task { await issue() } }.foregroundStyle(Theme.primary)
                }
                row("server.rack", "Server", Server.baseURL?.host ?? "—")
                row("number", "Version", "\(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?") (\(Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "?")) · \(BuildInfo.commit)")
                Text("Built \(BuildInfo.builtAt). The commit is the one on the Mac at build time; a + means it had uncommitted changes.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
            } header: { Text("This phone") }

            Section {
                Button(role: .destructive) { confirmSignOut = true } label: { Text("Sign out").frame(maxWidth: .infinity) }
            } footer: { Text("Ends this phone's sign-in on the server. The console and other phones stay signed in.") }

            Color.clear.frame(height: 80).listRowBackground(Color.clear).listRowInsets(EdgeInsets())
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Settings")
        .navigationBarTitleDisplayMode(.large)
        .confirmationDialog("Sign out of FamilyOS on this phone?", isPresented: $confirmSignOut, titleVisibility: .visible) {
            Button("Sign out", role: .destructive) { Task { await session.signOut() } }
            Button("Stay signed in", role: .cancel) {}
        }
        .sensoryFeedback(.success, trigger: copied)
        .task { await load() }
        .refreshable { await load() }
    }

    private func row(_ symbol: String, _ title: String, _ value: String) -> some View {
        HStack(spacing: Spacing.m) {
            Image(systemName: symbol).foregroundStyle(Theme.ink2).frame(width: 24).accessibilityHidden(true)
            Text(title).foregroundStyle(Theme.ink)
            Spacer()
            Text(value.isEmpty ? "—" : value).font(Theme.font(14)).foregroundStyle(Theme.ink3).lineLimit(1).truncationMode(.middle).frame(maxWidth: 180, alignment: .trailing)
        }
        .accessibilityElement(children: .combine)
    }

    private func load() async {
        do { household = try await API.shared.household(); devices = try await API.shared.devices(); error = nil; await session.refreshHousehold() }
        catch { self.error = error.localizedDescription }
    }
    private func linkTelegram() async {
        do {
            let link = try await API.shared.telegramLink()
            if let url = URL(string: link.url) { await UIApplication.shared.open(url) }
            error = nil
        } catch { self.error = error.localizedDescription }
    }
    private func issue() async {
        do { Server.deviceToken = try await API.shared.addDevice(label: "iPhone app").token; await load() } catch { self.error = error.localizedDescription }
    }
}

/// The phones and shortcuts that can send notices in, and the way to stop one.
struct DevicesView: View {
    let devices: [Device]
    let reload: () async -> Void
    @State private var error: String?
    var body: some View {
        List {
            if devices.isEmpty { Text("Nothing besides this app sends notices in yet.").foregroundStyle(Theme.ink3) }
            ForEach(devices) { d in
                VStack(alignment: .leading, spacing: 2) {
                    Text(d.label ?? "A device").foregroundStyle(Theme.ink)
                    Text("Added " + Format.dayYear.string(from: d.createdAt) + (d.lastUsedAt.map { " · last used " + Format.day.string(from: $0) } ?? " · never used")).font(Theme.font(12)).foregroundStyle(Theme.ink3)
                }
                .swipeActions { Button(role: .destructive) { Task { do { try await API.shared.revokeDevice(d.id); await reload() } catch { self.error = error.localizedDescription } } } label: { Label("Revoke", systemImage: "xmark") } }
            }
            if let error { Text(error).foregroundStyle(Theme.danger) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Phones and shortcuts")
    }
}

#Preview("Settings") { NavigationStack { SettingsView() }.environmentObject(PreviewData.session()) }
