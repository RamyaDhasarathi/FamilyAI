import SwiftUI

/// A person's profile, on one page: how they are reached, where they work, and, for a guardian, the details the emergency card and the school rules
/// use. Yours, or anyone's when a guardian opens it; the server shows each person only what they may see, and this screen draws only what came back.
/// Every field says why it is asked, and every one is optional.
struct ProfileView: View {
    @EnvironmentObject var session: Session
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    /// nil: the signed-in member's own profile.
    let memberId: UUID?
    @State private var profile: MemberProfile?
    @State private var loaded = false
    @State private var error: String?
    @State private var said: String?
    // phone
    @State private var phone = ""
    @State private var savingPhone = false
    // work
    @State private var query = ""
    @State private var suggestions: [PlaceSuggestion] = []
    @State private var picked: PlaceSuggestion?
    @State private var clearedPlace = false
    @State private var searching = false
    @State private var hasStart = false
    @State private var start = ProfileTime.date("09:00") ?? Date()
    @State private var savingWork = false
    // medical
    @State private var allergies = ""
    @State private var blood = ""
    @State private var savingMedical = false

    init(memberId: UUID? = nil) { self.memberId = memberId }

    private var targetId: UUID? { memberId ?? session.member?.id }
    private var guardian: Bool { session.member?.role == "guardian" }

    var body: some View {
        ScrollViewReader { proxy in
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let error, profile == nil {
                    ErrorState(text: error, retry: { Task { await load() } })
                } else if !loaded {
                    LoadingRows(count: 4)
                } else if let p = profile {
                    content(p)
                }
                BarSpace()
            }
            .padding(16)
        }
        .paper()
        .navigationTitle(profile?.isMe == false ? (profile?.displayName ?? "Profile") : "Your profile")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task {
            await load()
            // A debug launch can scroll to a card (`-scroll work|details`) so it can be looked at without tapping.
            if let target = Debug.string("scroll") { try? await Task.sleep(nanoseconds: 800_000_000); proxy.scrollTo(target, anchor: .top) }
        }
        }
    }

    @ViewBuilder private func content(_ p: MemberProfile) -> some View {
        header(p)
        if let error { Card { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger) } }
        if let said { Card { Text(said).font(Theme.font(14)).foregroundStyle(Theme.ink) } }
        contactCard(p)
        if !p.isChild {
            if p.isMe, let reach = p.reach {
                // One implementation, shared with My day: quiet hours, the daily cap and the morning message.
                ReachCard(prefs: reach, saved: { said = "Saved." })
            }
            workCard(p).id("work")
        }
        if guardian || p.isMe { detailsCard(p).id("details") }
    }

    private func header(_ p: MemberProfile) -> some View {
        HStack(spacing: 14) {
            if let m = session.members.first(where: { $0.id == p.id }) { Avatar(member: m, size: 56) }
            else { Glyph(symbol: "person.fill", tint: Theme.primary, size: 56) }
            VStack(alignment: .leading, spacing: 3) {
                Text(p.displayName).font(Theme.font(22, .medium, .serif)).foregroundStyle(Theme.ink)
                Text(p.role.capitalized + (p.isMe ? " · you" : "")).font(Theme.font(13)).foregroundStyle(Theme.ink3)
            }
        }
        .accessibilityElement(children: .combine).accessibilityAddTraits(.isHeader)
    }

    // MARK: how they are reached

    private func contactCard(_ p: MemberProfile) -> some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            Heading(title: p.isChild ? "About" : (p.isMe ? "How you are reached" : "How they are reached"))
            Card {
                VStack(alignment: .leading, spacing: Spacing.m) {
                    if let e = p.email { fact("Email", e, why: p.isMe ? "Where your sign-in link and mail go." : "Where their sign-in link and mail go.") }
                    if !p.isChild {
                        if p.isMe {
                            Text("Your phone number").font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                            Text("The number you forward WhatsApp messages from, so those land in your home. With its country code.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                            TextField("+91 98765 43210", text: $phone)
                                .keyboardType(.phonePad).textContentType(.telephoneNumber)
                                .font(Theme.font(15)).foregroundStyle(Theme.ink)
                                .padding(10).background(Theme.paper).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                                .accessibilityLabel("Your phone number with country code")
                            HStack {
                                Spacer()
                                if savingPhone { ProgressView().controlSize(.small) }
                                Button("Save number") { Task { await savePhone() } }
                                    .buttonStyle(.borderedProminent).tint(Theme.primary).controlSize(.small)
                                    .disabled(savingPhone || phone.filter(\.isNumber).count < 8 || phone.filter(\.isNumber) == (p.phone ?? ""))
                            }
                        } else {
                            fact("Phone", p.phone.map { "+" + $0 } ?? "not set", why: "The number their WhatsApp forwards come from.")
                        }
                        if let linked = p.telegramLinked {
                            fact("Telegram", linked ? "Linked" : "Not linked", why: linked ? "Reminders and questions can go that way too." : "Link it in Settings, under Connections.")
                        }
                    } else if p.school != nil || p.classLabel != nil {
                        fact("School", [p.school, p.classLabel.map { "class \($0)" }].compactMap { $0 }.joined(separator: ", "),
                             why: "Circulars are addressed by class, so this finds them. Changed on the web console.")
                    }
                }
            }
        }
    }

    private func fact(_ title: String, _ value: String, why: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack { Text(title).font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink); Spacer(); Text(value).font(Theme.font(15)).foregroundStyle(Theme.ink2).multilineTextAlignment(.trailing) }
            Text(why).font(Theme.font(12)).foregroundStyle(Theme.ink3)
        }
        .accessibilityElement(children: .combine)
    }

    // MARK: where they work

    private func workCard(_ p: MemberProfile) -> some View {
        let saved = p.work
        let changed = clearedPlace && saved?.place != nil || (picked != nil && picked?.label != saved?.place)
            || (hasStart ? ProfileTime.hhmm(start) : nil) != saved?.starts
        return VStack(alignment: .leading, spacing: Spacing.s) {
            Heading(title: p.isMe ? "Where you work" : "Where they work")
            Card {
                VStack(alignment: .leading, spacing: Spacing.m) {
                    Text("Used for the drive on Today. It is shown to \(p.isMe ? "you" : p.displayName.split(separator: " ").first.map(String.init) ?? "them") and to guardians, and to no one else. Skip it and nothing changes.")
                        .font(Theme.font(12)).foregroundStyle(Theme.ink3).fixedSize(horizontal: false, vertical: true)
                    if let chosen = picked ?? (clearedPlace ? nil : saved?.place.map({ PlaceSuggestion(label: $0, lat: saved?.lat ?? 0, lon: saved?.lon ?? 0) })) {
                        HStack(spacing: Spacing.s) {
                            Image(systemName: "mappin.and.ellipse").foregroundStyle(Theme.primary).accessibilityHidden(true)
                            Text(chosen.label).font(Theme.font(15)).foregroundStyle(Theme.ink).fixedSize(horizontal: false, vertical: true)
                            Spacer()
                            Button { picked = nil; clearedPlace = true; query = "" } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(Theme.ink3) }
                                .accessibilityLabel("Clear the work place")
                        }
                    } else {
                        TextField("An address, a landmark or a Maps link", text: $query)
                            .textInputAutocapitalization(.words).autocorrectionDisabled()
                            .font(Theme.font(15)).foregroundStyle(Theme.ink)
                            .padding(10).background(Theme.paper).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                            .accessibilityLabel("Search for the work place")
                        if searching { ProgressView().controlSize(.small) }
                        if query.trimmingCharacters(in: .whitespaces).count < 3 {
                            Text("Type at least three letters, or paste a Google Maps link.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                        }
                        ForEach(suggestions) { s in
                            Button { picked = s; clearedPlace = false; suggestions = [] } label: {
                                HStack(spacing: Spacing.s) {
                                    Image(systemName: "mappin").foregroundStyle(Theme.ink3).accessibilityHidden(true)
                                    Text(s.label).font(Theme.font(14)).foregroundStyle(Theme.ink).multilineTextAlignment(.leading)
                                    Spacer()
                                }
                                .padding(.vertical, 4)
                            }
                            .accessibilityHint("Use this place")
                        }
                    }
                    Toggle(isOn: $hasStart.animation(Motion.spring(reduceMotion))) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("A usual start time").font(Theme.font(15)).foregroundStyle(Theme.ink)
                            Text("So the drive is read for that hour.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                        }
                    }.tint(Theme.primary)
                    if hasStart {
                        DatePicker("Usual start", selection: $start, displayedComponents: .hourAndMinute).labelsHidden()
                            .accessibilityLabel("Usual start time")
                    }
                    HStack {
                        Spacer()
                        if savingWork { ProgressView().controlSize(.small) }
                        Button("Save") { Task { await saveWork(p) } }
                            .buttonStyle(.borderedProminent).tint(Theme.primary).controlSize(.small)
                            .disabled(savingWork || !changed)
                    }
                }
            }
        }
        .task(id: query) { await search() }
    }

    // MARK: health and school, for a guardian

    private func detailsCard(_ p: MemberProfile) -> some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            Heading(title: "For the emergency card")
            Card {
                VStack(alignment: .leading, spacing: Spacing.m) {
                    if let dob = p.dateOfBirth { fact("Birthday", Format.dayYear.string(from: dob), why: "So birthdays and ages are right. Changed on the Family page.") }
                    if guardian {
                        Text("Allergies").font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                        Text("Shown on the emergency card, so whoever helps knows.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                        TextField("Penicillin, peanuts", text: $allergies)
                            .font(Theme.font(15)).foregroundStyle(Theme.ink)
                            .padding(10).background(Theme.paper).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                            .accessibilityLabel("Allergies")
                        HStack {
                            Text("Blood group").font(Theme.font(15)).foregroundStyle(Theme.ink)
                            Spacer()
                            Picker("Blood group", selection: $blood) {
                                Text("Not set").tag("")
                                ForEach(BloodGroups.all, id: \.self) { Text($0).tag($0) }
                            }.labelsHidden().pickerStyle(.menu).tint(Theme.primary)
                        }
                        HStack {
                            Spacer()
                            if savingMedical { ProgressView().controlSize(.small) }
                            Button("Save") { Task { await saveMedical(p) } }
                                .buttonStyle(.borderedProminent).tint(Theme.primary).controlSize(.small)
                                .disabled(savingMedical || (allergies == (p.allergies ?? "") && blood == (p.bloodGroup ?? "")))
                        }
                    } else {
                        fact("Allergies", p.allergies ?? "none noted", why: "On the emergency card. A guardian changes it.")
                        fact("Blood group", p.bloodGroup ?? "not set", why: "On the emergency card. A guardian changes it.")
                    }
                }
            }
        }
    }

    // MARK: loading and saving

    private func load() async {
        guard let id = targetId else { return }
        do {
            let p = try await API.shared.memberProfile(id)
            profile = p; error = nil
            if !loaded { adopt(p) }
            loaded = true
        } catch { self.error = error.localizedDescription; loaded = true }
    }

    /// Fill the editors from what the server holds, once.
    private func adopt(_ p: MemberProfile) {
        phone = p.phone.map { "+" + $0 } ?? ""
        allergies = p.allergies ?? ""
        blood = p.bloodGroup ?? ""
        if let t = ProfileTime.date(p.work?.starts) { start = t; hasStart = true } else { hasStart = false }
    }

    private func search() async {
        let text = query.trimmingCharacters(in: .whitespaces)
        guard text.count >= 3, picked == nil else { suggestions = []; return }
        try? await Task.sleep(nanoseconds: 450_000_000)           // wait for the typing to pause
        if Task.isCancelled { return }
        searching = true; defer { searching = false }
        suggestions = (try? await API.shared.searchPlaces(text)) ?? []
    }

    private func savePhone() async {
        savingPhone = true; defer { savingPhone = false }
        do { try await API.shared.setMyPhone(phone); said = "Number saved."; error = nil; await reload() }
        catch { self.error = error.localizedDescription; said = nil }
    }

    private func saveWork(_ p: MemberProfile) async {
        savingWork = true; defer { savingWork = false }
        // A place already saved keeps its point; only a newly picked one sends a new point. Cleared sends nulls.
        let keep: PlaceSuggestion? = picked ?? (clearedPlace ? nil : p.work?.place.flatMap { label in
            guard let lat = p.work?.lat, let lon = p.work?.lon else { return nil }
            return PlaceSuggestion(label: label, lat: lat, lon: lon)
        })
        do {
            let updated = try await API.shared.setWork(p.id, place: keep, starts: hasStart ? ProfileTime.hhmm(start) : nil)
            profile = updated; picked = nil; clearedPlace = false; query = ""; said = "Saved."; error = nil
        } catch { self.error = error.localizedDescription; said = nil }
    }

    private func saveMedical(_ p: MemberProfile) async {
        savingMedical = true; defer { savingMedical = false }
        do { try await API.shared.setMedical(p.id, allergies: allergies.trimmingCharacters(in: .whitespaces), bloodGroup: blood); said = "Saved."; error = nil; await reload() }
        catch { self.error = error.localizedDescription; said = nil }
    }

    private func reload() async {
        guard let id = targetId, let p = try? await API.shared.memberProfile(id) else { return }
        profile = p
    }
}
