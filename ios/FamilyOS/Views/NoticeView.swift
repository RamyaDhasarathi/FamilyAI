import SwiftUI
import QuickLook

/// One notice as a task card: the picture if it is one, the title, its
/// tags, then Details, Dates and Activity, and the two things a person
/// does with a notice on the phone: handled, or handed over.
struct NoticeView: View {
    @EnvironmentObject var session: Session
    let artifactId: UUID
    let title: String

    @State private var artifact: Artifact?
    @State private var extraction: ArtifactExtraction?
    @State private var obligations: [Obligation] = []
    @State private var picture: UIImage?
    @State private var error: String?
    @State private var tab = "Details"
    @State private var handledNote = ""
    @State private var assignNote = ""
    @State private var assignTo: UUID?
    @State private var showHandled = false
    @State private var showAssign = false
    @State private var originalURL: URL?

    private var space: Space { Space.of(category: nil) }
    private var open: [Obligation] { obligations.filter { $0.status != "dismissed" } }
    private var due: Obligation? { open.filter { $0.dueDate != nil }.sorted { $0.dueDate! < $1.dueDate! }.first }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let picture {
                    Image(uiImage: picture).resizable().scaledToFill().frame(height: 220).clipped()
                        .clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
                }
                Card {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(alignment: .top, spacing: 12) {
                            Button { if artifact?.handledAt == nil { showHandled = true } else { Task { await reopen() } } } label: {
                                Image(systemName: artifact?.handledAt == nil ? "circle" : "checkmark.circle.fill").font(Theme.font(24)).foregroundStyle(artifact?.handledAt == nil ? Theme.ink3 : Theme.green).frame(width: 44, height: 44)
                            }.buttonStyle(.plain).accessibilityLabel(artifact?.handledAt == nil ? "Mark done" : "Done; tap to reopen")
                            Text(artifact?.headline ?? title).font(Theme.font(20, .semibold)).foregroundStyle(Theme.ink)
                        }
                        HStack(spacing: 8) {
                            if let a = artifact { Tag(text: a.channel == "gmail" ? "Mail" : a.channel.capitalized, symbol: a.isPicture ? "photo" : "tray", tint: Theme.ink3) }
                            if let d = due, let date = d.dueDate { Tag(text: "By " + Format.day.string(from: date), symbol: "calendar", tint: Theme.primary) }
                            if let a = artifact, a.visibility == "shared" { Tag(text: "Household", symbol: "person.2", tint: Theme.green) }
                        }
                        if let a = artifact, let sender = a.sender { Text("From \(sender)").font(Theme.font(13)).foregroundStyle(Theme.ink3) }
                    }
                }
                HStack(spacing: 18) {
                    ForEach(["Details", "Dates", "Activity"], id: \.self) { name in
                        Button { withAnimation(.snappy) { tab = name } } label: {
                            VStack(spacing: 6) {
                                HStack(spacing: 4) {
                                    Text(name).font(Theme.font(14, .semibold))
                                    if name == "Dates", !open.isEmpty { Text("\(open.count)").font(Theme.font(11)).padding(.horizontal, 6).padding(.vertical, 1).background(Theme.primaryTint).clipShape(Capsule()) }
                                }
                                Rectangle().fill(tab == name ? Theme.primary : .clear).frame(height: 2)
                            }.foregroundStyle(tab == name ? Theme.primary : Theme.ink3)
                        }.buttonStyle(.plain)
                    }
                    Spacer()
                }.padding(.horizontal, 4)
                switch tab {
                case "Dates": datesTab
                case "Activity": activityTab
                default: detailsTab
                }
                HStack(spacing: 10) {
                    if artifact?.handledAt == nil {
                        GhostButton(title: "Hand to someone") { showAssign = true }
                        PrimaryButton(title: "Mark handled") { showHandled = true }
                    } else {
                        GhostButton(title: "Not handled after all") { Task { await reopen() } }
                    }
                }
                if let a = artifact, !a.isPicture {
                    Button { Task { await openOriginal() } } label: { Label("Open the original", systemImage: "doc.text.magnifyingglass").font(Theme.font(14, .medium)).foregroundStyle(Theme.primary) }.padding(.horizontal, 4)
                }
                ErrorLine(text: error)
                BarSpace()
            }
            .padding(16)
        }
        .paper()
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .refreshable { await load() }
        .quickLookPreview($originalURL)
        .sensoryFeedback(.success, trigger: artifact?.handledAt)
        .alert("Handled", isPresented: $showHandled) {
            TextField("A word back, optional", text: $handledNote)
            Button("Mark handled") { Task { await handled() } }
            Button("Cancel", role: .cancel) {}
        } message: { Text("Its reminders stop and whoever handed it over is told.") }
        .sheet(isPresented: $showAssign) { assignSheet }
    }

    private var detailsTab: some View {
        Card(padding: 6) {
            VStack(alignment: .leading, spacing: 0) {
                if let x = extraction {
                    if let e = x.extraction {
                        if e.claims.isEmpty { Text(e.nonActionableReason ?? "Nothing dated was read from it.").foregroundStyle(Theme.ink3).padding(8) }
                        ForEach(e.claims) { c in ClaimRow(c: c).padding(8); if c.id != e.claims.last?.id { Divider() } }
                    } else if let status = x.jobStatus {
                        Text(status == "failed" ? (x.jobError ?? "The read failed.") : "Being read (\(status))…").foregroundStyle(Theme.ink3).padding(8)
                    }
                } else { Text("Reading…").foregroundStyle(Theme.ink3).padding(8) }
                if let note = artifact?.note, !note.isEmpty { Divider(); Text("Note: \(note)").font(Theme.font(13)).foregroundStyle(Theme.ink2).padding(8) }
            }
        }
    }

    private var datesTab: some View {
        Card(padding: 6) {
            VStack(spacing: 0) {
                if obligations.isEmpty { Text("No dates on this notice.").foregroundStyle(Theme.ink3).padding(8) }
                ForEach(obligations) { o in ObligationRow(o: o) { s in await decide(o.id, s) }.padding(8); if o.id != obligations.last?.id { Divider() } }
            }
        }
    }

    private var activityTab: some View {
        Card(padding: 6) {
            VStack(alignment: .leading, spacing: 0) {
                if let a = artifact {
                    ActivityLine(symbol: "tray.and.arrow.down", text: "Arrived " + Format.stamp.string(from: a.receivedAt))
                    if let to = a.assignedTo { Divider(); ActivityLine(symbol: "person.crop.circle.badge.plus", text: "Handed to \(session.name(of: to) ?? "someone")" + (a.assignedNote.map { ": “\($0)”" } ?? "")) }
                    if let when = a.handledAt { Divider(); ActivityLine(symbol: "checkmark.circle", text: "Handled " + Format.day.string(from: when) + (a.handledNote.map { " — \($0)" } ?? "")) }
                    let tagged = a.subjectMemberIds.compactMap { session.name(of: $0) }
                    if !tagged.isEmpty { Divider(); ActivityLine(symbol: "tag", text: "About " + tagged.joined(separator: ", ")) }
                }
            }
        }
    }

    private var assignSheet: some View {
        NavigationStack {
            Form {
                Picker("To", selection: $assignTo) {
                    Text("Nobody (take it back)").tag(UUID?.none)
                    ForEach(session.members.filter { !$0.isChild }) { m in Text(m.displayName).tag(UUID?.some(m.id)) }
                }
                TextField("A note for them", text: $assignNote)
            }
            .navigationTitle("Hand over")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Hand over") { Task { await assign() } } }
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { showAssign = false } }
            }
        }
        .presentationDetents([.medium])
    }

    private func load() async {
        do { artifact = try await API.shared.artifact(artifactId); error = nil } catch { self.error = error.localizedDescription; return }
        extraction = try? await API.shared.extraction(artifactId)
        let ids = Set([artifactId] + (artifact?.children ?? []))
        obligations = ((try? await API.shared.obligations(status: "")) ?? []).filter { ids.contains($0.artifactId) && $0.supersededAt == nil }
        if artifact?.isPicture == true, picture == nil, let data = try? await API.shared.picture(artifactId) { picture = UIImage(data: data) }
    }
    private func decide(_ id: UUID, _ status: String) async {
        error = await session.doOrKeep(label: "The decision", keep: { Outbox.keep(kind: .decide, target: id, status: status, label: "\(status) a date") }) {
            _ = try await API.shared.decide(id, status, requestId: UUID().uuidString)
        }
        await load()
    }
    private func handled() async {
        let note = handledNote.isEmpty ? nil : handledNote
        error = await session.doOrKeep(label: "Marking it handled", keep: { Outbox.keep(kind: .handled, target: artifactId, note: note, label: "mark \(title) handled") }) {
            _ = try await API.shared.handled(artifactId, note: note, requestId: UUID().uuidString)
        }
        handledNote = ""; await load()
    }
    private func reopen() async { do { _ = try await API.shared.reopen(artifactId); await load() } catch { self.error = error.localizedDescription } }
    private func assign() async {
        let note = assignNote.isEmpty ? nil : assignNote
        error = await session.doOrKeep(label: "The hand-over", keep: { Outbox.keep(kind: .assign, target: artifactId, member: assignTo, note: note, label: "hand \(title) over") }) {
            _ = try await API.shared.assign(artifactId, to: assignTo, note: note, requestId: UUID().uuidString)
        }
        showAssign = false; await load()
    }
    private func openOriginal() async {
        do {
            let (data, type) = try await API.shared.original(artifactId)
            let ext = type.contains("pdf") ? "pdf" : type.contains("html") ? "html" : type.hasPrefix("text/") ? "txt" : "bin"
            let url = FileManager.default.temporaryDirectory.appendingPathComponent(artifactId.uuidString).appendingPathExtension(ext)
            try data.write(to: url, options: .atomic); originalURL = url
        } catch { self.error = error.localizedDescription }
    }
}

struct ActivityLine: View {
    let symbol: String; let text: String
    var body: some View {
        HStack(spacing: 10) { Image(systemName: symbol).foregroundStyle(Theme.ink3).frame(width: 20); Text(text).font(Theme.font(14)).foregroundStyle(Theme.ink2); Spacer() }.padding(8)
    }
}

struct ObligationRow: View {
    let o: Obligation
    let decide: (String) async -> Void
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: o.status == "accepted" ? "checkmark.circle.fill" : o.status == "dismissed" ? "xmark.circle" : "circle")
                .font(Theme.font(20)).foregroundStyle(o.status == "accepted" ? Theme.green : Theme.ink3).padding(.top, 1)
            VStack(alignment: .leading, spacing: 4) {
                Text(o.title).foregroundStyle(Theme.ink).strikethrough(o.status == "dismissed")
                HStack(spacing: 6) {
                    if let when = Format.when(o.dueDate, o.dueTime) { Text(when) }
                    Text("· \(o.action)")
                    if o.optional { Text("· optional") }
                }.font(.caption).foregroundStyle(Theme.ink3)
                if o.status == "proposed" {
                    HStack(spacing: 8) {
                        Button("Accept") { Task { await decide("accepted") } }.buttonStyle(.borderedProminent).tint(Theme.primary).controlSize(.small)
                        Button("Dismiss") { Task { await decide("dismissed") } }.buttonStyle(.bordered).controlSize(.small)
                    }.padding(.top, 2)
                }
            }
            Spacer()
        }
    }
}

struct ClaimRow: View {
    let c: Claim
    var body: some View {
        HStack(spacing: 10) {
            Glyph(symbol: c.kind == "payment" || c.kind == "deadline" ? "indianrupeesign.circle" : c.kind == "document" ? "doc.text" : "calendar", tint: Theme.ink3, size: 30)
            VStack(alignment: .leading, spacing: 2) {
                Text(c.title).foregroundStyle(Theme.ink)
                HStack(spacing: 6) {
                    Text(c.kind)
                    if let d = c.date { Text("· " + Format.dayYear.string(from: d)) }
                    if let t = c.timeText { Text("· " + t) }
                    if let a = c.amountText { Text("· " + a) }
                    if let p = c.place { Text("· " + p) }
                    if c.uncertain { Text("· uncertain") }
                }.font(.caption).foregroundStyle(Theme.ink3)
            }
            Spacer()
        }
    }
}
