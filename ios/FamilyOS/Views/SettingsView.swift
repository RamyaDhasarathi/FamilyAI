import SwiftUI

/// Settings, in eight short groups: you, your people, privacy and security, what is connected, how reminders reach you, the day-to-day
/// screens that live here for now, this phone, and the way out. Each thing is in one place; what the web console still owns is said once.
struct SettingsView: View {
    @EnvironmentObject var session: Session
    @Environment(\.switchTab) private var switchTab
    @State private var household: Household?
    @State private var devices: [Device] = []
    @State private var error: String?
    @State private var confirmSignOut = false
    @State private var copied = false
    /// Whether this server has WhatsApp reading switched on: the entry is not shown otherwise.
    @State private var whatsAppAvailable = false

    private var telegramLinked: Bool { session.member?.telegramLinked ?? false }

    var body: some View {
        ScrollViewReader { proxy in
            list.task {
                // A debug launch can scroll to a group (`-scroll notifications|home|about`) so each can be looked at without tapping.
                if let target = Debug.string("scroll") { try? await Task.sleep(nanoseconds: 1_200_000_000); proxy.scrollTo(target, anchor: .top) }
            }
        }
    }

    private var list: some View {
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
                    NavigationLink { ProfileView() } label: { Label("Your profile", systemImage: "person.text.rectangle") }
                        .accessibilityHint("Your number, work place, quiet hours and morning message")
                }
            }
            if let error { Section { ErrorState(text: error) { Task { await load() } } }.listRowInsets(EdgeInsets()).listRowBackground(Color.clear) }
            if session.outboxLeft > 0 {
                Section { OfflineBanner() }.listRowInsets(EdgeInsets()).listRowBackground(Color.clear)
            }

            Section {
                Button { switchTab("family") } label: {
                    HStack(spacing: Spacing.m) {
                        Image(systemName: "person.2").foregroundStyle(Theme.ink2).frame(width: 24).accessibilityHidden(true)
                        Text("Family members and invites").foregroundStyle(Theme.ink)
                        Spacer()
                        Text("\(session.members.count)").foregroundStyle(Theme.ink3)
                        Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.ink3).accessibilityHidden(true)
                    }
                }
                .accessibilityLabel("Family members and invites, \(session.members.count) people. Opens Family.")
            } header: { Text("People") } footer: { Text("Roles, schools and the standing rules are managed on the web console.") }

            Section {
                NavigationLink { SecurityView() } label: { Label("Privacy and security", systemImage: "lock.shield") }
            } footer: { Text("The family key, where your words are read, and passkeys.") }

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
                    row("paperplane", "Telegram", telegramLinked ? "Linked · @\(bot)" : "Not linked · @\(bot)")
                    Button(telegramLinked ? "Link another device" : "Link my Telegram") { Task { await linkTelegram() } }.foregroundStyle(Theme.primary)
                    Text("Opens Telegram on this phone; press Start and the bot says who it linked. Then reminders and questions can go that way too.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                }
                if whatsAppAvailable { NavigationLink { WhatsAppView() } label: { Label("WhatsApp reading", systemImage: "bubble.left.and.text.bubble.right") } }
                NavigationLink { DevicesView(devices: devices, reload: { await load() }) } label: {
                    HStack(spacing: Spacing.m) {
                        Image(systemName: "iphone").foregroundStyle(Theme.ink2).frame(width: 24)
                        Text("Phones and shortcuts").foregroundStyle(Theme.ink)
                        Spacer()
                        Text("\(devices.count)").foregroundStyle(Theme.ink3)
                    }
                }
                NavigationLink { AssistantsView() } label: { Label("My assistants", systemImage: "sparkles") }
            } header: { Text("Connections") } footer: {
                Text("Mailboxes are managed on the web. Each connection sends notices in; none of them lets FamilyOS send on your behalf without a tap.")
            }

            RemindersSection(alsoSentBy: "Mail" + (telegramLinked ? " and Telegram" : "")).id("notifications")
            LocationSection()
            HealthSection()

            Section("Your day and home") {
                NavigationLink { MyDayView() } label: { Label("My day", systemImage: "sun.max") }
                NavigationLink { FamilyMapView() } label: { Label("Family map", systemImage: "point.3.connected.trianglepath.dotted") }
                NavigationLink { QuarantineView() } label: { Label("Held mail", systemImage: "tray.full") }
                NavigationLink { SchoolDayView() } label: { Label("School: tomorrow, forms, absence", systemImage: "backpack") }
                NavigationLink { EmergencyView() } label: { Label("Emergency card", systemImage: "cross.case") }
                NavigationLink { RulesView() } label: { Label("Rules and access", systemImage: "lock.shield") }
                NavigationLink { MemoryView() } label: { Label("What FamilyOS knows", systemImage: "brain.head.profile") }
                NavigationLink { ActivityView() } label: { Label("Activity and undo", systemImage: "clock.arrow.circlepath") }
                NavigationLink { WarrantiesView() } label: { Label("Returns and warranties", systemImage: "shippingbox") }
            }
            .id("home")

            Section("Money and care") {
                NavigationLink { StandingView() } label: { Label("Bills and standing payments", systemImage: "indianrupeesign.circle") }
                NavigationLink { CareListView() } label: { Label("Looking after someone", systemImage: "heart.text.square") }
                NavigationLink { HandoffsView() } label: { Label("Handed over", systemImage: "arrowshape.turn.up.right") }
                NavigationLink { WorkloadView() } label: { Label("Who carries what", systemImage: "person.2") }
                NavigationLink { CircleView() } label: { Label("Circle and grants", systemImage: "person.badge.key") }
                NavigationLink { WhatIfView() } label: { Label("What if", systemImage: "questionmark.circle") }
                NavigationLink { DigestView() } label: { Label("Weekly digest", systemImage: "envelope.open") }
            }
            .id("care")

            Section("Records") {
                NavigationLink { ConsentsView() } label: { Label("Consent for children", systemImage: "checkmark.seal") }
                NavigationLink { IntakeGapsView() } label: { Label("What did not arrive", systemImage: "tray.and.arrow.down") }
                NavigationLink { RailsView() } label: { Label("How notices arrive", systemImage: "arrow.triangle.branch") }
                NavigationLink { SittingsView() } label: { Label("Sign-in sittings", systemImage: "safari") }
                NavigationLink { ExportErasureView() } label: { Label("Export and erase", systemImage: "square.and.arrow.up") }
            }
            .id("records")

            Section {
                NavigationLink { AboutPhoneView() } label: { Label("About this phone", systemImage: "info.circle") }
            }
            .id("about")

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
        if session.member?.isChild == true { whatsAppAvailable = false }
        else { let status = try? await API.shared.whatsApp(); whatsAppAvailable = status?.available ?? false }
    }
    private func linkTelegram() async {
        do {
            let link = try await API.shared.telegramLink()
            if let url = URL(string: link.url) { await UIApplication.shared.open(url) }
            error = nil
        } catch { self.error = error.localizedDescription }
    }
}

/// What this phone is running and where it talks to: the server, the build, and whether the share sheet has its own token (issued and revoked under Phones and shortcuts).
struct AboutPhoneView: View {
    var body: some View {
        List {
            Section {
                row("server.rack", "Server", Server.baseURL?.host ?? "—")
                row("number", "Version", "\(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?") (\(Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "?")) · \(BuildInfo.commit)")
                row("key", "Share-sheet token", Server.deviceToken != nil ? "Issued" : "Not issued")
            } footer: {
                Text("Built \(BuildInfo.builtAt). The commit is the one on the Mac at build time; a + means it had uncommitted changes. The share-sheet token is issued and revoked under Phones and shortcuts.")
            }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("About this phone")
    }

    private func row(_ symbol: String, _ title: String, _ value: String) -> some View {
        HStack(spacing: Spacing.m) {
            Image(systemName: symbol).foregroundStyle(Theme.ink2).frame(width: 24).accessibilityHidden(true)
            Text(title).foregroundStyle(Theme.ink)
            Spacer()
            Text(value.isEmpty ? "—" : value).font(Theme.font(14)).foregroundStyle(Theme.ink3).lineLimit(1).truncationMode(.middle).frame(maxWidth: 220, alignment: .trailing)
        }
        .accessibilityElement(children: .combine)
    }
}

/// The phones and shortcuts that can send notices in, the share sheet's own token on this phone, and the way to stop one.
struct DevicesView: View {
    let devices: [Device]
    let reload: () async -> Void
    @State private var error: String?
    @State private var issued = Server.deviceToken != nil
    var body: some View {
        List {
            Section {
                if issued {
                    Text("The share sheet sends with its own token, listed below as “iPhone app”. Revoking it there stops the share sheet, not the app.").font(Theme.font(13)).foregroundStyle(Theme.ink2)
                } else {
                    Button("Issue a token for the share sheet") { Task { await issue() } }.foregroundStyle(Theme.primary)
                }
            } header: { Text("Share sheet on this phone") }
            Section {
                if devices.isEmpty { Text("Nothing besides this app sends notices in yet.").foregroundStyle(Theme.ink3) }
                ForEach(devices) { d in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(d.label ?? "A device").foregroundStyle(Theme.ink)
                        Text("Added " + Format.dayYear.string(from: d.createdAt) + (d.lastUsedAt.map { " · last used " + Format.day.string(from: $0) } ?? " · never used")).font(Theme.font(12)).foregroundStyle(Theme.ink3)
                    }
                    .swipeActions { Button(role: .destructive) { Task { do { try await API.shared.revokeDevice(d.id); await reload() } catch { self.error = error.localizedDescription } } } label: { Label("Revoke", systemImage: "xmark") } }
                }
            } header: { Text("Devices") }
            if let error { Text(error).foregroundStyle(Theme.danger) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Phones and shortcuts")
    }
    private func issue() async {
        do { Server.deviceToken = try await API.shared.addDevice(label: "iPhone app").token; issued = true; error = nil; await reload() } catch { self.error = error.localizedDescription }
    }
}

/// Phones and shortcuts on its own, loading its own list (a debug launch opens it directly: `-tab screen-phones`).
struct DevicesLoader: View {
    @State private var devices: [Device] = []
    var body: some View {
        DevicesView(devices: devices, reload: { devices = (try? await API.shared.devices()) ?? devices })
            .task { devices = (try? await API.shared.devices()) ?? [] }
    }
}

#Preview("Settings") { NavigationStack { SettingsView() }.environmentObject(PreviewData.session()) }
