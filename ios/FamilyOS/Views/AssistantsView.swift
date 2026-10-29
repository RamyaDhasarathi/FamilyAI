import SwiftUI
import UniformTypeIdentifiers

/// My assistants: an instruction sent to my own Claude or Grok and its
/// answer as text, the outside servers I allow, the keys an assistant of
/// mine connects with, and what FamilyOS was taught by showing it.
/// Everything here reads and proposes; nothing in a reply is done. Keys
/// are typed once, sent to the server, sealed there, and never kept here.
struct AssistantsView: View {
    @EnvironmentObject var session: Session
    @State private var connections: [AssistantConnection] = []
    @State private var tasks: [AssistantTask] = []
    @State private var servers: [McpServer] = []
    @State private var agents: [AgentKey] = []
    @State private var loaded = false
    @State private var error: String?
    private let preview: Bool

    init(preview: Snapshot? = nil) {
        if let p = preview {
            _connections = State(initialValue: p.connections); _tasks = State(initialValue: p.tasks)
            _servers = State(initialValue: p.servers); _agents = State(initialValue: p.agents); _loaded = State(initialValue: true)
        }
        self.preview = preview != nil
    }

    /// Sample content for previews.
    struct Snapshot { var connections: [AssistantConnection]; var tasks: [AssistantTask]; var servers: [McpServer]; var agents: [AgentKey] }

    private var anyLive: Bool { tasks.contains(where: \.isLive) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 12) {
                    Glyph(symbol: "sparkles", tint: Theme.primary, size: 44)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("My assistants").font(Theme.font(24, .medium, .serif)).foregroundStyle(Theme.ink)
                        Text("They read as you and only propose").font(Theme.font(13)).foregroundStyle(Theme.ink3)
                    }
                }
                .accessibilityElement(children: .combine).accessibilityAddTraits(.isHeader)
                if session.member?.isChild == true {
                    EmptyState(symbol: "person.badge.shield.checkmark", title: "For grown-ups", text: "Connecting an assistant or an outside server is for the adults in the household.")
                } else {
                    if let error { ErrorState(text: error, retry: { Task { await load() } }) }
                    if !loaded && error == nil { LoadingRows(count: 3) }
                    else {
                        AskAssistantSection(connections: $connections, tasks: $tasks, reload: load)
                        OutsideServersSection(servers: $servers, reload: load)
                        ConnectAssistantSection(agents: $agents, reload: load)
                    }
                    Heading(title: "What FamilyOS was taught")
                    ListCard {
                        NavigationLink { SkillsView() } label: {
                            TaskRow(symbol: "hand.tap", tint: Theme.primary, title: "Skills shown to it", detail: "Open, tap, swipe and read only. Run or forget them.")
                        }.buttonStyle(.plain)
                    }
                }
                BarSpace()
            }
            .padding(16)
        }
        .paper()
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task { if !preview { await load() } }
        // While a task is queued or running, ask again every 2.5 s; the loop
        // ends when nothing is live, and is cancelled when the screen goes.
        .task(id: anyLive) {
            guard anyLive, !preview else { return }
            for _ in 0..<90 {
                try? await Task.sleep(for: .milliseconds(2500))
                if Task.isCancelled { return }
                if let fresh = try? await API.shared.assistantTasks() { tasks = fresh }
                if !anyLive { return }
            }
        }
    }

    private func load() async {
        do {
            connections = try await API.shared.assistantConnections()
            tasks = try await API.shared.assistantTasks()
            servers = (try? await API.shared.mcpServers()) ?? []
            agents = (try? await API.shared.agentKeys()) ?? []
            error = nil
        } catch { self.error = error.localizedDescription }
        loaded = true
    }
}

// MARK: ask my assistant

private struct AskAssistantSection: View {
    @Binding var connections: [AssistantConnection]
    @Binding var tasks: [AssistantTask]
    let reload: () async -> Void
    @State private var instruction = ""
    @State private var target: UUID?
    @State private var sending = false
    @State private var error: String?
    @State private var showConnections = false
    @State private var removing: AssistantConnection?

    var body: some View {
        Heading(title: "Ask my assistant")
        Text("Send an instruction to your own Claude or Grok. It looks at FamilyOS as you, can only read and propose, and answers in text. Its key is yours, kept sealed on the server and never shown again.")
            .font(Theme.font(12)).foregroundStyle(Theme.ink3)
        if connections.isEmpty {
            Card { Text("Add a connection to start.").font(Theme.font(14)).foregroundStyle(Theme.ink3) }
        } else {
            Card {
                VStack(alignment: .leading, spacing: Spacing.m) {
                    TextField("What needs me this week, and what can wait?", text: $instruction, axis: .vertical)
                        .lineLimit(2...6).font(Theme.font(15)).foregroundStyle(Theme.ink)
                        .padding(10).background(Theme.paper).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    HStack {
                        Text("Send to").font(Theme.font(14)).foregroundStyle(Theme.ink3)
                        Picker("Send to", selection: $target) {
                            ForEach(connections) { c in Text("\(c.label) (\(c.usedToday) of \(c.dailyCap) today)").tag(Optional(c.id)) }
                        }
                        .labelsHidden().pickerStyle(.menu).tint(Theme.primary)
                        Spacer()
                        if sending { ProgressView().controlSize(.small) }
                        Button("Send") { Task { await send() } }.buttonStyle(.borderedProminent).tint(Theme.primary).controlSize(.small)
                            .disabled(sending || instruction.trimmingCharacters(in: .whitespacesAndNewlines).count < 3)
                    }
                    if let error { Text(error).font(Theme.font(12)).foregroundStyle(Theme.danger) }
                }
            }
            if !tasks.isEmpty {
                VStack(spacing: Spacing.s) { ForEach(tasks) { TaskCard(task: $0) } }
            }
        }
        DisclosureGroup(isExpanded: $showConnections) {
            VStack(alignment: .leading, spacing: Spacing.m) {
                if !connections.isEmpty {
                    ListCard {
                        ForEach(connections) { c in
                            HStack {
                                TaskRow(symbol: "key", tint: Theme.primary, title: c.label,
                                        detail: [providerName(c.provider), c.model, "up to \(c.dailyCap) a day"].compactMap { $0 }.joined(separator: " · "), trailing: .none)
                                Button("Remove") { removing = c }.font(Theme.font(13, .semibold)).foregroundStyle(Theme.danger).padding(.trailing, Spacing.s)
                            }
                            if c.id != connections.last?.id { RowDivider() }
                        }
                    }
                }
                AddConnectionForm(added: reload)
            }
            .padding(.top, Spacing.s)
        } label: {
            Text("Connections (\(connections.count))").font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
        }
        .tint(Theme.ink3)
        .onAppear { if connections.isEmpty { showConnections = true }; if target == nil { target = connections.first?.id } }
        .onChange(of: connections) { _, new in if target == nil || !new.contains(where: { $0.id == target }) { target = new.first?.id } }
        .confirmationDialog("Remove \(removing?.label ?? "this connection")?", isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } }), titleVisibility: .visible) {
            Button("Remove and forget its key", role: .destructive) { if let c = removing { Task { await remove(c) } } }
        }
    }

    private func providerName(_ p: String) -> String {
        AddConnectionForm.providers.first { $0.0 == p }.map { String($0.1.split(separator: ",").first ?? "") } ?? p
    }

    private func send() async {
        guard let target else { return }
        sending = true; defer { sending = false }
        do {
            _ = try await API.shared.sendAssistantTask(connection: target, instruction: instruction.trimmingCharacters(in: .whitespacesAndNewlines))
            instruction = ""; error = nil
            tasks = (try? await API.shared.assistantTasks()) ?? tasks
            connections = (try? await API.shared.assistantConnections()) ?? connections
        } catch { self.error = error.localizedDescription }
    }

    private func remove(_ c: AssistantConnection) async {
        do { try await API.shared.removeAssistantConnection(c.id); await reload() }
        catch { self.error = error.localizedDescription }
    }
}

/// One instruction and where it stands; the reply, when there is one, as text.
private struct TaskCard: View {
    let task: AssistantTask
    private var state: AgentState {
        switch task.status {
        case "queued": return .planning
        case "running": return .working
        case "done": return .done
        default: return .failed
        }
    }
    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: Spacing.s) {
                HStack(alignment: .top) {
                    Text(task.instruction).font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                    Spacer(minLength: Spacing.s)
                    AgentStatusBadge(state: state)
                }
                Text(task.label + " · " + Format.stamp.string(from: task.createdAt)).font(Theme.font(12)).foregroundStyle(Theme.ink3)
                if task.status == "failed" { Text("Did not work: " + (task.error ?? "no answer")).font(Theme.font(13)).foregroundStyle(Theme.danger) }
                if let r = task.result, !r.isEmpty {
                    Text(r).font(Theme.font(14)).foregroundStyle(Theme.ink2).textSelection(.enabled)
                        .padding(10).frame(maxWidth: .infinity, alignment: .leading)
                        .background(Theme.paper).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    Text("Your assistant's reply, as text. Nothing in it has been done.").font(Theme.font(11)).foregroundStyle(Theme.ink3)
                }
            }
        }
    }
}

/// A new connection. The API key is typed into a secure field, sent once,
/// and cleared from memory as soon as the server has it.
private struct AddConnectionForm: View {
    static let providers = [("claude", "Claude, my API key (needs a public address)"),
                            ("grok", "Grok, my xAI key (needs a public address)"),
                            ("claude_code", "Claude Code on this server (works here, development)")]
    let added: () async -> Void
    @State private var provider = "claude"
    @State private var label = ""
    @State private var apiKey = ""
    @State private var model = ""
    @State private var cap = 20
    @State private var saving = false
    @State private var error: String?

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: Spacing.m) {
                Picker("Assistant", selection: $provider) { ForEach(Self.providers, id: \.0) { Text($0.1).tag($0.0) } }
                    .pickerStyle(.menu).tint(Theme.primary)
                Text("Claude and Grok answer from their makers' clouds and call FamilyOS back over the internet, so this server needs a public address. Claude Code runs on the server itself.")
                    .font(Theme.font(12)).foregroundStyle(Theme.ink3)
                field { TextField("Name, for example My Claude", text: $label).textInputAutocapitalization(.words) }
                if provider != "claude_code" {
                    field { SecureField("API key, pasted once then sealed", text: $apiKey).textContentType(.password).autocorrectionDisabled().textInputAutocapitalization(.never) }
                }
                field { TextField("Model (optional)", text: $model).autocorrectionDisabled().textInputAutocapitalization(.never) }
                Stepper("At most \(cap) a day", value: $cap, in: 1...200).font(Theme.font(14)).foregroundStyle(Theme.ink)
                HStack {
                    if let error { Text(error).font(Theme.font(12)).foregroundStyle(Theme.danger) }
                    Spacer()
                    if saving { ProgressView().controlSize(.small) }
                    Button("Add connection") { Task { await add() } }.buttonStyle(.borderedProminent).tint(Theme.primary).controlSize(.small)
                        .disabled(saving || (provider != "claude_code" && apiKey.count < 12))
                }
            }
        }
    }

    private func field<F: View>(@ViewBuilder _ f: () -> F) -> some View {
        f().font(Theme.font(15)).padding(10).background(Theme.paper).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private func add() async {
        saving = true; defer { saving = false }
        do {
            try await API.shared.addAssistantConnection(provider: provider, label: label, apiKey: provider == "claude_code" ? "" : apiKey, model: model, dailyCap: cap)
            apiKey = ""; label = ""; model = ""; error = nil
            await added()
        } catch { apiKey = ""; self.error = error.localizedDescription }
    }
}

// MARK: outside servers

private struct OutsideServersSection: View {
    @Binding var servers: [McpServer]
    let reload: () async -> Void
    @State private var label = ""
    @State private var url = ""
    @State private var auth = ""
    @State private var saving = false
    @State private var error: String?

    var body: some View {
        Heading(title: "Outside servers")
        Text("Other MCP servers you choose to use: https only, no private addresses. You tick which tools may be called and you make each call. What comes back is not kept.")
            .font(Theme.font(12)).foregroundStyle(Theme.ink3)
        if !servers.isEmpty {
            ListCard {
                ForEach(servers) { s in
                    NavigationLink { McpServerView(server: s, changed: reload) } label: {
                        TaskRow(symbol: "server.rack", tint: Theme.primary, title: s.label,
                                detail: "\(s.url) · \(s.allowedTools.count) tool\(s.allowedTools.count == 1 ? "" : "s") allowed")
                    }
                    .buttonStyle(.plain)
                    if s.id != servers.last?.id { RowDivider() }
                }
            }
            Text("Open one to choose its tools, try one, or remove it.").font(Theme.font(11)).foregroundStyle(Theme.ink3)
        }
        Card {
            VStack(alignment: .leading, spacing: Spacing.m) {
                field { TextField("Name, for example School library", text: $label) }
                field { TextField("https://…/mcp", text: $url).keyboardType(.URL).textContentType(.URL).autocorrectionDisabled().textInputAutocapitalization(.never) }
                field { SecureField("Access key, if it needs one", text: $auth).textContentType(.password).autocorrectionDisabled().textInputAutocapitalization(.never) }
                HStack {
                    if let error { Text(error).font(Theme.font(12)).foregroundStyle(Theme.danger) }
                    Spacer()
                    if saving { ProgressView().controlSize(.small) }
                    Button("Add server") { Task { await add() } }.buttonStyle(.borderedProminent).tint(Theme.primary).controlSize(.small)
                        .disabled(saving || label.trimmingCharacters(in: .whitespaces).isEmpty || !url.lowercased().hasPrefix("https://"))
                }
            }
        }
    }

    private func field<F: View>(@ViewBuilder _ f: () -> F) -> some View {
        f().font(Theme.font(15)).padding(10).background(Theme.paper).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private func add() async {
        saving = true; defer { saving = false }
        do {
            _ = try await API.shared.addMcpServer(label: label, url: url, auth: auth)
            label = ""; url = ""; auth = ""; error = nil
            await reload()
        } catch { auth = ""; self.error = error.localizedDescription }
    }

}

/// One outside server: tick which of its tools may be called, then call one.
/// Its descriptions and its answers are text from a stranger, shown as such.
struct McpServerView: View {
    let server: McpServer
    let changed: () async -> Void
    @State private var tools: McpTools?
    @State private var allowed: Set<String> = []
    @State private var error: String?
    @State private var said: String?
    @State private var tool = ""
    @State private var arguments = "{}"
    @State private var calling = false
    @State private var answer: McpCallResult?
    @State private var answerError: String?
    @State private var askRemove = false
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 12) {
                    Glyph(symbol: "server.rack", tint: Theme.primary, size: 44)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(server.label).font(Theme.font(24, .medium, .serif)).foregroundStyle(Theme.ink)
                        Text(server.url).font(Theme.font(13)).foregroundStyle(Theme.ink3).lineLimit(1).truncationMode(.middle)
                    }
                }
                if let error { ErrorState(text: error, retry: { Task { await load() } }) }
                if let t = tools {
                    Text(t.notice).font(Theme.font(12)).foregroundStyle(Theme.warning)
                    Heading(title: "Tools it offers")
                    if t.tools.isEmpty { Card { Text("It lists no tools.").font(Theme.font(14)).foregroundStyle(Theme.ink3) } }
                    else {
                        ListCard {
                            ForEach(t.tools) { x in
                                Toggle(isOn: Binding(get: { allowed.contains(x.name) }, set: { on in if on { allowed.insert(x.name) } else { allowed.remove(x.name) } })) {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(x.name).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                                        if !x.description.isEmpty { Text(x.description).font(Theme.font(12)).foregroundStyle(Theme.ink3) }
                                    }
                                }
                                .tint(Theme.primary).padding(.horizontal, 10).padding(.vertical, 8)
                                if x.id != t.tools.last?.id { RowDivider(inset: 10) }
                            }
                        }
                        HStack {
                            if let said { Text(said).font(Theme.font(12)).foregroundStyle(Theme.success) }
                            Spacer()
                            Button("Save allowed tools") { Task { await save() } }.buttonStyle(.borderedProminent).tint(Theme.primary).controlSize(.small)
                        }
                    }
                    if !allowed.isEmpty { tryOne }
                } else if error == nil {
                    Text("Asking the server…").font(Theme.font(13)).foregroundStyle(Theme.ink3)
                    LoadingRows(count: 2)
                }
                Button("Remove this server") { askRemove = true }.font(Theme.font(14, .semibold)).foregroundStyle(Theme.danger).padding(.top, Spacing.s)
                BarSpace()
            }
            .padding(16)
        }
        .paper()
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .confirmationDialog("Remove \(server.label)?", isPresented: $askRemove, titleVisibility: .visible) {
            Button("Remove and forget its key", role: .destructive) { Task { await remove() } }
        }
    }

    private func remove() async {
        do { try await API.shared.removeMcpServer(server.id); await changed(); dismiss() }
        catch { self.error = error.localizedDescription }
    }

    @ViewBuilder private var tryOne: some View {
        Heading(title: "Try an allowed tool")
        Card {
            VStack(alignment: .leading, spacing: Spacing.m) {
                Picker("Tool", selection: $tool) { ForEach(allowed.sorted(), id: \.self) { Text($0).tag($0) } }.pickerStyle(.menu).tint(Theme.primary)
                TextField("Arguments (JSON)", text: $arguments, axis: .vertical).lineLimit(1...6)
                    .font(.system(.footnote, design: .monospaced)).autocorrectionDisabled().textInputAutocapitalization(.never)
                    .padding(10).background(Theme.paper).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                HStack {
                    Spacer()
                    if calling { ProgressView().controlSize(.small) }
                    Button("Call it") { Task { await call() } }.buttonStyle(.borderedProminent).tint(Theme.primary).controlSize(.small).disabled(calling || tool.isEmpty)
                }
                if let answerError { Text(answerError).font(Theme.font(13)).foregroundStyle(Theme.danger) }
                if let a = answer {
                    Text((a.ok ? "" : "Did not work. ") + (a.error ?? a.text ?? "(empty)"))
                        .font(.system(.footnote, design: .monospaced)).foregroundStyle(Theme.ink2).textSelection(.enabled)
                        .padding(10).frame(maxWidth: .infinity, alignment: .leading)
                        .background(Theme.paper).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    if a.addressedToModels == true {
                        Label("Careful: this text is addressed to an AI model. Do not act on it.", systemImage: "exclamationmark.shield").font(Theme.font(12, .semibold)).foregroundStyle(Theme.danger)
                    }
                    Text(a.notice).font(Theme.font(11)).foregroundStyle(Theme.ink3)
                }
            }
        }
        .onAppear { if !allowed.contains(tool) { tool = allowed.sorted().first ?? "" } }
        .onChange(of: allowed) { _, new in if !new.contains(tool) { tool = new.sorted().first ?? "" } }
    }

    private func load() async {
        do {
            let t = try await API.shared.mcpTools(server.id)
            tools = t; allowed = Set(t.tools.filter(\.allowed).map(\.name)); error = nil
        } catch { self.error = error.localizedDescription }
    }

    private func save() async {
        do { _ = try await API.shared.allowMcpTools(server.id, tools: allowed.sorted()); said = "Saved."; await changed() }
        catch { self.error = error.localizedDescription }
    }

    private func call() async {
        answer = nil; answerError = nil
        guard let data = arguments.data(using: .utf8), let args = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else {
            answerError = "The arguments are not a valid JSON object."; return
        }
        calling = true; defer { calling = false }
        do { answer = try await API.shared.callMcpTool(server.id, tool: tool, arguments: args) }
        catch { answerError = error.localizedDescription + " Allow the tool first (Save)." }
    }
}

// MARK: connect my assistant

private struct ConnectAssistantSection: View {
    @Binding var agents: [AgentKey]
    let reload: () async -> Void
    @State private var label = ""
    @State private var days = 90
    @State private var canShare = false
    @State private var saving = false
    @State private var error: String?
    /// The new key, held only while it is on screen.
    @State private var issued: AgentIssued?
    @State private var disconnecting: AgentKey?
    private static let until: DateFormatter = { let f = DateFormatter(); f.dateFormat = "d MMM"; return f }()

    var body: some View {
        Heading(title: "Connect my assistant")
        Text("Connect your own assistant (Grok Bot, Claude, ChatGPT, any MCP client). It sees what you see, can propose things for you to confirm, and shares with the family only if you allow it.")
            .font(Theme.font(12)).foregroundStyle(Theme.ink3)
        ListCard {
            if agents.isEmpty { Text("None connected.").font(Theme.font(14)).foregroundStyle(Theme.ink3).padding(10).frame(maxWidth: .infinity, alignment: .leading) }
            ForEach(agents) { k in
                HStack {
                    TaskRow(symbol: "link", tint: k.active ? Theme.primary : Theme.ink3, title: k.label, detail: line(k), trailing: .none)
                    if k.active { Button("Disconnect") { disconnecting = k }.font(Theme.font(13, .semibold)).foregroundStyle(Theme.danger).padding(.trailing, Spacing.s) }
                }
                if k.id != agents.last?.id { RowDivider() }
            }
        }
        if let issued { IssuedKey(issued: issued, done: { self.issued = nil }) }
        Card {
            VStack(alignment: .leading, spacing: Spacing.m) {
                TextField("Its name, for example Grok Bot", text: $label).font(Theme.font(15))
                    .padding(10).background(Theme.paper).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                Stepper("Lasts \(days) day\(days == 1 ? "" : "s")", value: $days, in: 1...365, step: days < 30 ? 1 : 15).font(Theme.font(14)).foregroundStyle(Theme.ink)
                Toggle("May share a note with the family", isOn: $canShare).font(Theme.font(14)).foregroundStyle(Theme.ink).tint(Theme.primary)
                HStack {
                    if let error { Text(error).font(Theme.font(12)).foregroundStyle(Theme.danger) }
                    Spacer()
                    if saving { ProgressView().controlSize(.small) }
                    Button("Connect") { Task { await connect() } }.buttonStyle(.borderedProminent).tint(Theme.primary).controlSize(.small)
                        .disabled(saving || label.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
        .onDisappear { issued = nil }
        .confirmationDialog("Disconnect \(disconnecting?.label ?? "this assistant")?", isPresented: Binding(get: { disconnecting != nil }, set: { if !$0 { disconnecting = nil } }), titleVisibility: .visible) {
            Button("Disconnect now", role: .destructive) { if let k = disconnecting { Task { await disconnect(k) } } }
        }
    }

    private func line(_ k: AgentKey) -> String {
        let state = k.active ? "connected until " + Self.until.string(from: k.expiresAt) : (k.revokedAt != nil ? "disconnected" : "expired")
        return state + (k.canShare ? " · may share with the family" : " · read and propose only") + " · \(k.calls7D) calls this week"
    }

    private func connect() async {
        saving = true; defer { saving = false }
        do {
            issued = try await API.shared.connectAgent(label: label, canShare: canShare, days: days)
            label = ""; error = nil
            agents = (try? await API.shared.agentKeys()) ?? agents
        } catch { self.error = error.localizedDescription }
    }

    private func disconnect(_ k: AgentKey) async {
        do { try await API.shared.disconnectAgent(k.id); await reload() }
        catch { self.error = error.localizedDescription }
    }
}

/// A key shown once: the address and the key to paste into the assistant.
/// Copying puts it on this phone's pasteboard only, for two minutes.
private struct IssuedKey: View {
    let issued: AgentIssued
    let done: () -> Void
    @State private var copied: String?

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.m) {
            Label("Shown once", systemImage: "key").font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
            Text("In your assistant, add a custom MCP connector with this address and key.").font(Theme.font(13)).foregroundStyle(Theme.ink2)
            if let address = API.shared.agentAddress { copyRow("Address", address) }
            copyRow("Key", issued.token)
            Text("It can: " + issued.can.joined(separator: "; ") + ". A hosted assistant needs this server reachable from the internet.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
            Button("I have copied it", action: done).font(Theme.font(14, .semibold)).foregroundStyle(Theme.primary)
        }
        .padding(Spacing.l).frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.warning.opacity(0.10)).clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous).stroke(Theme.warning.opacity(0.35), lineWidth: 0.5))
    }

    private func copyRow(_ name: String, _ value: String) -> some View {
        HStack(spacing: Spacing.s) {
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(Theme.font(11, .semibold)).foregroundStyle(Theme.ink3).textCase(.uppercase)
                Text(value).font(.system(.footnote, design: .monospaced)).foregroundStyle(Theme.ink).textSelection(.enabled).lineLimit(3)
            }
            Spacer(minLength: 0)
            Button(copied == name ? "Copied" : "Copy") {
                UIPasteboard.general.setItems([[UTType.plainText.identifier: value]], options: [.localOnly: true, .expirationDate: Date().addingTimeInterval(120)])
                copied = name
            }
            .buttonStyle(.bordered).controlSize(.small)
        }
    }
}

#if DEBUG
extension PreviewData {
    static let assistants = AssistantsView.Snapshot(
        connections: decode("""
        [{"id":"f0000000-0000-0000-0000-000000000001","provider":"claude","label":"My Claude","model":null,"daily_cap":20,"created_at":"\(day(-3))T09:00:00+05:30","used_today":2}]
        """),
        tasks: decode("""
        [{"id":"f1000000-0000-0000-0000-000000000002","instruction":"Is anything due for Lily before Diwali?","status":"running","result":null,"error":null,"label":"My Claude","created_at":"\(day(0))T08:40:00+05:30","completed_at":null},
         {"id":"f1000000-0000-0000-0000-000000000001","instruction":"What needs me this week, and what can wait?","status":"done","result":"Three things need you: the Term 2 fee by Friday, the science fair form by Thursday, and the PTM today at 9. The Diwali holidays can wait; they are already in the calendar.","error":null,"label":"My Claude","created_at":"\(day(0))T07:55:00+05:30","completed_at":"\(day(0))T07:56:10+05:30"}]
        """),
        servers: decode("""
        [{"id":"f2000000-0000-0000-0000-000000000001","label":"School library","url":"https://library.example.org/mcp","allowed_tools":["search_books"],"has_credential":true,"created_at":"\(day(-10))T10:00:00+05:30"}]
        """),
        agents: decode("""
        [{"id":"f3000000-0000-0000-0000-000000000001","label":"Grok Bot","can_share":false,"created_at":"\(day(-20))T10:00:00+05:30","expires_at":"\(day(70))T10:00:00+05:30","revoked_at":null,"last_used_at":null,"calls_7d":14,"active":true}]
        """))
}

#Preview("My assistants") { NavigationStack { AssistantsView(preview: PreviewData.assistants) }.environmentObject(PreviewData.session()) }
#Preview("My assistants · dark") {
    NavigationStack { AssistantsView(preview: PreviewData.assistants) }.environmentObject(PreviewData.session()).preferredColorScheme(.dark)
}
#endif
