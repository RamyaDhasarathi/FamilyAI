import SwiftUI
import PhotosUI

/// Ask: a conversation against the household's own record. Every answer
/// cites the notices it came from. What the model suggests doing is a
/// suggestion until a person taps it; then the ordinary endpoint does it,
/// the card says so, and what can be undone offers Undo. An errand is
/// written down and approved on its own screen, never run from here.
struct AskView: View {
    @EnvironmentObject var session: Session
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var question = ""
    @State private var turns: [Turn] = []
    @State private var busy = false
    @State private var asking: Task<Void, Never>?
    @State private var lastQuestion: String?
    /// The answer so far, while it is still being written.
    @State private var partial = ""
    @State private var error: String?
    @State private var photo: PhotosPickerItem?
    @State private var bills: [BriefItem] = []
    @State private var openErrand: Errand?
    @FocusState private var typing: Bool
    /// A question handed in from elsewhere (an offer on Family), ready to send.
    init(prefill: String? = nil) { _question = State(initialValue: prefill ?? "") }

    struct Turn: Identifiable {
        let id = UUID()
        let q: String
        var a: ChatTurn?
        var done: [Int: Outcome] = [:]
        var system: String? = nil
    }
    /// What happened to a suggestion once tapped: what was done, and how to undo it if that exists.
    struct Outcome { let said: String; let undo: (() async throws -> Void)? }

    private var suggestions: [(String, String)] {
        var out = [("calendar", "What's on this week?"), ("person.2", "Who is handling what?")]
        for c in session.members.filter(\.isChild).prefix(2) { out.append(("graduationcap", "Find \(c.displayName.split(separator: " ").first.map(String.init) ?? c.displayName)'s latest school circular")) }
        if let b = bills.first { out.append(("indianrupeesign.circle", "When is \(b.title.replacingOccurrences(of: "Pay ", with: "")) due?")) }
        out.append(("airplane", "Plan a weekend away"))
        return out
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: Spacing.l) {
                            if turns.isEmpty { welcome }
                            ForEach(Array(turns.enumerated()), id: \.element.id) { i, t in
                                TurnView(turn: t, members: session.members, perform: { p, j in await perform(p, turn: i, index: j) },
                                         undo: { j in await undo(turn: i, index: j) })
                                    .id(t.id)
                            }
                            if busy {
                                if !partial.isEmpty {
                                    Text(partial).font(Theme.font(15)).foregroundStyle(Theme.ink)
                                        .padding(.horizontal, Spacing.gutter).accessibilityLabel("Answer so far: \(partial)")
                                }
                                HStack(spacing: Spacing.m) {
                                    ProgressView().tint(Theme.primary)
                                    Text(partial.isEmpty ? "Looking through the record…" : "Still writing…").font(Theme.font(14)).foregroundStyle(Theme.ink3)
                                    Spacer()
                                    Button("Stop") { asking?.cancel() }.font(Theme.font(14, .semibold)).foregroundStyle(Theme.primary)
                                }
                                .padding(.horizontal, Spacing.gutter).id("busy")
                                .accessibilityElement(children: .combine)
                            }
                            if let error {
                                ErrorState(text: error, retry: lastQuestion == nil ? nil : { question = lastQuestion ?? ""; Task { await ask() } }).padding(.horizontal, Spacing.gutter)
                            }
                            Color.clear.frame(height: 8).id("end")
                        }
                        .padding(.top, Spacing.s)
                    }
                    .scrollDismissesKeyboard(.interactively)
                    .onChange(of: turns.count) { _, _ in withAnimation(Motion.gentle(reduceMotion)) { proxy.scrollTo("end", anchor: .bottom) } }
                    .onChange(of: busy) { _, now in if now { withAnimation(Motion.gentle(reduceMotion)) { proxy.scrollTo("end", anchor: .bottom) } } }
                }
                composer
            }
            .paper()
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(for: UUID.self) { id in NoticeView(artifactId: id, title: "Notice") }
            .navigationDestination(for: Errand.self) { e in ErrandView(errandId: e.id) }
            .navigationDestination(item: $openErrand) { e in ErrandView(errandId: e.id) }
            .task { bills = ((try? await API.shared.brief())?.items ?? []).filter { $0.action == "pay" } }
            .onChange(of: photo) { _, item in if let item { Task { await attach(item) } } }
        }
    }

    // MARK: pieces

    private var welcome: some View {
        VStack(spacing: Spacing.xl) {
            HStack {
                Spacer()
                ProfileButton()
            }.padding(.horizontal, Spacing.gutter)
            Orb(size: 76, on: true).padding(.top, Spacing.s)
            VStack(spacing: Spacing.s) {
                Text("What do you need?").font(Theme.font(28, .regular, .serif)).foregroundStyle(Theme.ink)
                Text("Answers come from the family's own notices, with the source beside each one.").font(Theme.font(14)).foregroundStyle(Theme.ink3).multilineTextAlignment(.center).padding(.horizontal, Spacing.xl)
            }
            VStack(spacing: Spacing.s) {
                ForEach(suggestions, id: \.1) { symbol, text in
                    Button { question = text; Task { await ask() } } label: {
                        HStack(spacing: Spacing.s) {
                            Image(systemName: symbol).foregroundStyle(Theme.primary).frame(width: 22)
                            Text(text).foregroundStyle(Theme.ink).multilineTextAlignment(.leading)
                            Spacer(minLength: 0)
                        }
                        .font(Theme.font(15, .medium)).padding(.horizontal, Spacing.l).padding(.vertical, 12).frame(minHeight: 44)
                        .background(Theme.card).clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(Theme.line, lineWidth: 0.5))
                    }.buttonStyle(.plain)
                }
            }.padding(.horizontal, Spacing.gutter)
        }.frame(maxWidth: .infinity)
    }

    private var composer: some View {
        GlassGroup(spacing: 16) {
            HStack(alignment: .bottom, spacing: Spacing.s) {
                PhotosPicker(selection: $photo, matching: .images) {
                    Image(systemName: "plus").font(Theme.font(17, .semibold)).foregroundStyle(Theme.ink).frame(width: 44, height: 44).glassCircle()
                }
                .accessibilityLabel("Attach a photo to share with FamilyOS")
                TextField("Ask, or say what to do…", text: $question, axis: .vertical).lineLimit(1...4).focused($typing)
                    .font(Theme.font(16)).padding(.horizontal, Spacing.l).padding(.vertical, 11).glassCapsule(interactive: false)
                    .submitLabel(.send).onSubmit { Task { await ask() } }
                Button { Task { await ask() } } label: {
                    Image(systemName: "arrow.up").font(Theme.font(16, .bold)).foregroundStyle(.white)
                        .frame(width: 44, height: 44).glassCircle(tint: Theme.primary)
                }
                .disabled(busy || question.trimmingCharacters(in: .whitespaces).isEmpty)
                .opacity(busy || question.trimmingCharacters(in: .whitespaces).isEmpty ? 0.5 : 1)
                .accessibilityLabel("Send")
            }
        }
        .padding(.horizontal, Spacing.gutter).padding(.top, Spacing.s).padding(.bottom, 100)
        .sensoryFeedback(.success, trigger: turns.count)
    }

    // MARK: asking

    private func ask() async {
        let q = question.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty, !busy else { return }
        question = ""; lastQuestion = q; error = nil
        turns.append(Turn(q: q))
        busy = true
        let history = turns.dropLast().compactMap { t -> [ChatMessage]? in t.a.map { [ChatMessage(role: "user", content: t.q), ChatMessage(role: "assistant", content: $0.say)] } }.flatMap { $0 }.suffix(12)
        partial = ""
        let task = Task {
            do {
                var a: ChatTurn?
                for try await ev in API.shared.chatStream(q, history: Array(history)) {
                    if Task.isCancelled { return }
                    switch ev {
                    case .say(let said): partial = said.replacing(/\s*\[[A-Za-z]+\d*\]/, with: "")
                    case .turn(let t): a = t
                    }
                }
                guard let a else { throw APIError(status: 502, detail: "The answer stopped before it was finished.") }
                if let i = turns.lastIndex(where: { $0.q == q && $0.a == nil }) { turns[i].a = a }
            } catch is CancellationError {
                turns.removeAll { $0.q == q && $0.a == nil }; question = q
            } catch {
                turns.removeAll { $0.q == q && $0.a == nil }
                self.error = error.localizedDescription
            }
        }
        asking = task
        await task.value
        if task.isCancelled { turns.removeAll { $0.q == q && $0.a == nil }; question = q }
        busy = false; partial = ""
    }

    /// A photo from the library, shared the way the share sheet shares: a
    /// private notice that the reader will turn into dates and claims.
    private func attach(_ item: PhotosPickerItem) async {
        defer { photo = nil }
        guard let data = try? await item.loadTransferable(type: Data.self) else { error = "That photo could not be read."; return }
        let said = await session.doOrKeep(label: "The photo", keep: { Outbox.keepShare(data: data, contentType: "image/jpeg", tag: nil, note: "from Ask", shared: false, label: "a photo from Ask") }) {
            _ = try await API.shared.share(data: data, contentType: "image/jpeg", tag: nil, note: "from Ask", shared: false, requestId: UUID().uuidString)
        }
        turns.append(Turn(q: "Shared a photo", a: nil, system: said ?? "Shared with FamilyOS. It is being read; its dates and claims will appear on Today and in the Inbox."))
    }

    // MARK: doing what was suggested

    private func perform(_ p: ChatProposal, turn: Int, index: Int) async {
        do {
            var outcome: Outcome
            switch p.kind {
            case "assign":
                guard let a = p.artifactId else { return }
                _ = try await API.shared.assign(a, to: p.memberId, note: p.note)
                outcome = Outcome(said: "Handed to \(p.memberName ?? "them")", undo: { _ = try await API.shared.assign(a, to: nil, note: nil) })
            case "todo":
                let t = try await API.shared.addTodo(title: p.title ?? "To do", dueDate: p.dueDate, dueTime: p.dueTime.map { String($0.prefix(5)) }, assignedTo: p.memberId, note: p.note)
                outcome = Outcome(said: "Added to the to-dos", undo: { _ = try await API.shared.setTodoDone(t.id, true) })
            case "handled":
                guard let a = p.artifactId else { return }
                _ = try await API.shared.handled(a, note: p.note)
                outcome = Outcome(said: "Marked handled", undo: { _ = try await API.shared.reopen(a) })
            case "decide":
                guard let o = p.obligationId, let s = p.status else { return }
                _ = try await API.shared.decide(o, s)
                outcome = Outcome(said: s == "accepted" ? "Accepted; it is on the calendar" : "Dismissed", undo: nil)
            case "plan":
                _ = try await API.shared.draftPlan(brief: p.brief ?? p.title ?? "", shape: p.shape ?? "trip")
                outcome = Outcome(said: "Drafted under Life › Plans. Nothing is booked.", undo: nil)
            case "errand":
                guard let service = p.service else { return }
                let e = try await API.shared.proposeErrand(service: service, look: p.look ?? true, title: p.title ?? p.what ?? "Errand", what: p.what ?? p.title ?? "",
                                                           details: p.note, dueDate: p.dueDate, dueTime: p.dueTime, part: nil, maxAmount: nil, currency: nil)
                outcome = Outcome(said: e.status == "proposed" ? "Written down. A guardian approves it on its own screen." : "Written down and ready to run on this phone.", undo: { _ = try await API.shared.cancelErrand(e.id) })
                openErrand = e
            default:
                return
            }
            turns[turn].done[index] = outcome; error = nil
        } catch { self.error = error.localizedDescription }
    }

    private func undo(turn: Int, index: Int) async {
        guard let u = turns[turn].done[index]?.undo else { return }
        do { try await u(); turns[turn].done[index] = nil; error = nil } catch { self.error = error.localizedDescription }
    }
}

/// One exchange: the question as the person's bubble, the answer with its
/// sources, then the suggestions, each either waiting or done.
struct TurnView: View {
    let turn: AskView.Turn
    let members: [Member]
    let perform: (ChatProposal, Int) async -> Void
    let undo: (Int) async -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.m) {
            HStack {
                Spacer(minLength: 48)
                Text(turn.q).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                    .padding(.horizontal, Spacing.l).padding(.vertical, 10)
                    .background(Theme.primary.opacity(0.12)).clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
            }
            .accessibilityLabel("You asked: \(turn.q)")
            if let s = turn.system {
                Label(s, systemImage: "checkmark.circle").font(Theme.font(13)).foregroundStyle(Theme.ink3)
            }
            if let a = turn.a {
                VStack(alignment: .leading, spacing: Spacing.s) {
                    HStack(spacing: 6) {
                        Image(systemName: "sparkle").font(Theme.font(11, .bold)).foregroundStyle(Theme.primary)
                        Text("FamilyOS").font(Theme.font(12, .semibold)).foregroundStyle(Theme.ink3)
                        if !a.grounded && a.note == nil { Tag(text: "Not from the record", tint: Theme.warning) }
                    }
                    Text(a.say).font(Theme.font(16)).foregroundStyle(Theme.ink).lineSpacing(2).textSelection(.enabled)
                    if let note = a.note { Label(note, systemImage: "exclamationmark.triangle").font(Theme.font(12)).foregroundStyle(Theme.warning) }
                    if !a.citations.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: Spacing.s) {
                                ForEach(a.citations, id: \.self) { c in
                                    if let id = c.artifactId {
                                        NavigationLink(value: id) { Tag(text: c.text, symbol: "doc.text", tint: Theme.ink2) }.buttonStyle(.plain)
                                            .accessibilityLabel("Source: \(c.text)")
                                    } else { Tag(text: c.text, symbol: "doc.text", tint: Theme.ink3) }
                                }
                            }
                        }
                    }
                }
                .padding(Spacing.l).background(Theme.card).clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous).stroke(Theme.line, lineWidth: 0.5))
                ForEach(Array(a.proposals.enumerated()), id: \.offset) { j, p in
                    SuggestionCard(p: p, members: members, outcome: turn.done[j], perform: { await perform(p, j) }, undo: { await undo(j) })
                }
            }
        }
        .padding(.horizontal, Spacing.gutter)
    }
}

/// A suggestion: what would be done, to whom, and the one button. Once
/// done it says so, and offers Undo where the server allows it.
struct SuggestionCard: View {
    let p: ChatProposal
    let members: [Member]
    let outcome: AskView.Outcome?
    let perform: () async -> Void
    let undo: () async -> Void
    @State private var busy = false

    private var text: String {
        switch p.kind {
        case "assign": return "Hand \(p.headline ?? "the notice") to \(p.memberName ?? "?")" + (p.note.map { " — “\($0)”" } ?? "")
        case "todo": return "To-do: \(p.title ?? "")" + (p.dueDate.map { " by " + Format.day.string(from: $0) } ?? "") + (p.memberName.map { " — \($0)’s" } ?? "")
        case "handled": return "Mark \(p.headline ?? "the notice") handled" + (p.note.map { " — “\($0)”" } ?? "")
        case "decide": return "\(p.status == "accepted" ? "Accept" : "Dismiss") \(p.title ?? p.headline ?? "the date")"
        case "plan": return "Plan \(p.title ?? "this"): an itinerary, candidate bookings, the legwork as to-dos."
        case "errand": return "\(p.look == true ? "Look on" : "Errand on") \(p.label ?? p.service ?? ""): \(p.what ?? p.title ?? "")"
        default: return p.title ?? p.kind
        }
    }
    private var buttonTitle: String {
        switch p.kind {
        case "errand": return "Write it down"
        case "plan": return "Draft it"
        default: return "Do it"
        }
    }
    private var affects: [Member] { members.filter { $0.id == p.memberId } }
    private var never: String? {
        switch p.kind {
        case "errand": return "Nothing runs until a guardian approves exactly this. Nothing is paid."
        case "plan": return "Nothing is booked."
        default: return nil
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            HStack(alignment: .top, spacing: Spacing.s) {
                AgentStatusBadge(state: outcome == nil ? .suggested : .done)
                Spacer()
                if let outcome, outcome.undo != nil {
                    Button(busy ? "…" : "Undo") { Task { busy = true; await undo(); busy = false } }.font(Theme.font(13, .semibold)).foregroundStyle(Theme.primary).disabled(busy)
                        .accessibilityLabel("Undo: \(text)")
                }
            }
            Text(text).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
            if let why = p.why, !p.ok { Text(why).font(Theme.font(13)).foregroundStyle(Theme.ink3) }
            if !affects.isEmpty {
                HStack(spacing: 6) {
                    Text("Affects").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                    ForEach(affects) { m in HStack(spacing: 4) { Avatar(member: m, size: 18); Text(m.displayName).font(Theme.font(12, .medium)).foregroundStyle(Theme.ink2) } }
                }
            }
            if let outcome {
                Label(outcome.said, systemImage: "checkmark").font(Theme.font(13)).foregroundStyle(Theme.success)
            } else if p.ok {
                if let never { Text(never).font(Theme.font(12)).foregroundStyle(Theme.ink3) }
                Button { Task { busy = true; await perform(); busy = false } } label: {
                    Text(busy ? "Working…" : buttonTitle).font(Theme.font(14, .semibold)).frame(maxWidth: .infinity).padding(.vertical, 4)
                }
                .buttonStyle(.borderedProminent).tint(Theme.primary).disabled(busy)
                .accessibilityLabel("\(buttonTitle): \(text)")
            }
        }
        .padding(Spacing.l).frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.primary.opacity(p.ok ? 0.07 : 0.03)).clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous).stroke(Theme.primary.opacity(p.ok ? 0.25 : 0.1), lineWidth: 0.5))
        .animation(.default, value: outcome == nil)
    }
}

#Preview("Ask · empty") { AskView().environmentObject(PreviewData.session()) }
