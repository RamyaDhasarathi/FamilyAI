import SwiftUI
import WebKit

/// One errand, which is one piece of the agent's work: what it is, where
/// it stands, exactly what a guardian is approving, what happened step by
/// step with the pictures, and the phone as its browser when it runs here.
/// Every state the server knows is a state the screen shows; nothing is
/// shown as done that the server has not said is done.
struct ErrandView: View {
    @EnvironmentObject var session: Session
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let errandId: UUID
    @State private var errand: Errand?
    @State private var error: String?
    @State private var running = false
    @State private var ended: String?
    @State private var confirmCancel = false
    @State private var busy = false

    private var state: AgentState { errand.map { AgentState(errand: $0.status) } ?? .planning }
    private var mine: Bool { errand?.createdBy == session.member?.id }
    private var guardian: Bool { session.member?.role == "guardian" }

    var body: some View {
        VStack(spacing: 0) {
            if running {
                PhoneBrowser(errandId: errandId, onEnded: { said in ended = said; running = false; Task { await load() } })
                HStack {
                    Text(ended ?? "FamilyOS is driving this page. Touch it to take over at any time.").font(Theme.font(12)).foregroundStyle(Theme.ink3).lineLimit(2)
                    Spacer()
                    Button("Stop") { running = false; Task { await load() } }.font(Theme.font(14, .semibold)).foregroundStyle(Theme.primary)
                }.padding(Spacing.m).background(Theme.paper)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: Spacing.l) {
                        if let e = errand { content(e) }
                        else if let error { ErrorState(text: error) { Task { await load() } } }
                        else { LoadingRows(count: 2) }
                        if let error, errand != nil { ErrorLine(text: error) }
                        BarSpace()
                    }.padding(Spacing.gutter)
                }
            }
        }
        .paper()
        .navigationTitle(errand?.title ?? "Errand")
        .navigationBarTitleDisplayMode(.inline)
        .confirmationDialog("Cancel this errand?", isPresented: $confirmCancel, titleVisibility: .visible) {
            Button("Cancel the errand", role: .destructive) { Task { await cancel() } }
            Button("Keep it", role: .cancel) {}
        } message: { Text("It will not run. Anything already done on the site stays as it is.") }
        .sensoryFeedback(.success, trigger: errand?.status)
        .task { await load() }
        .refreshable { await load() }
    }

    @ViewBuilder
    private func content(_ e: Errand) -> some View {
        // Where it stands.
        Card {
            VStack(alignment: .leading, spacing: Spacing.s) {
                HStack(alignment: .top) {
                    AgentStatusBadge(state: state)
                    Spacer()
                    Tag(text: serviceLabel(e), symbol: e.isPhoneApp ? "iphone" : "globe", tint: Theme.ink3)
                }
                Text(e.title).font(Theme.font(20, .semibold)).foregroundStyle(Theme.ink)
                if e.what != e.title { Text(e.what).font(Theme.font(14)).foregroundStyle(Theme.ink2) }
                Text(explain(e)).font(Theme.font(13)).foregroundStyle(Theme.ink3)
                if let err = e.error, state == .failed || state == .needsYou { Label(err, systemImage: "exclamationmark.triangle").font(Theme.font(13)).foregroundStyle(Theme.warning) }
            }
        }
        if let said = ended { Card { Text(said).font(Theme.font(14)).foregroundStyle(Theme.ink2) } }

        // What is being approved, before anything runs.
        if state == .waitingApproval || state == .planning {
            ApprovalSummary(action: e.kind == "look" ? "Look, and report back" : "Book, up to the limit, pay after the service",
                            lines: approvalLines(e), affects: session.members.filter { $0.id == e.createdBy },
                            never: e.stopRules.isEmpty ? ["Nothing is paid by FamilyOS; it never holds a card", "It stops before any last step a person must take"] : Array(e.stopRules.prefix(4)),
                            fingerprint: e.paramsSha256)
        }

        // The one action for this state.
        if state == .waitingApproval {
            if guardian, let sha = e.paramsSha256 {
                PrimaryButton(title: e.isPhoneApp ? "Approve" : "Approve and run on this phone") { Task { await approve(sha: sha) } }
                Text(e.isPhoneApp ? "Approving binds this exact text. It runs when the FamilyOS driver is started on the asker's phone." : "Runs here, in the app's own browser, with your own sign-in.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
            } else {
                Card { Label("Waiting for a guardian to approve it.", systemImage: "hand.raised").foregroundStyle(Theme.ink3) }
            }
        } else if e.isPhoneApp, state == .planning || state == .needsYou || state == .working {
            Card {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Read through the phone's own hands").font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                    Text("\(e.appLabel ?? e.service) is an app, not a site, so this does not run in a web view. A Mac starts the FamilyOS driver on this phone; it opens the app, reads the screen and hands the words in as a private notice. Nothing is typed and nothing is bought.").font(Theme.font(13)).foregroundStyle(Theme.ink2)
                    if let url = API.shared.phoneSocketURL(e.id) {
                        Button("Copy the driver's address") { UIPasteboard.general.string = url.absoluteString }.font(Theme.font(14, .semibold)).foregroundStyle(Theme.primary)
                    }
                }
            }
        } else if (state == .planning || state == .needsYou || state == .working), mine {
            PrimaryButton(title: state == .needsYou ? "Open and finish on this phone" : state == .working ? "Open the page it is on" : "Run on this phone") { ended = nil; running = true }
            if state == .needsYou {
                HStack(spacing: Spacing.s) {
                    GhostButton(title: "Try again") { ended = nil; running = true }
                    GhostButton(title: "Mark it done") { Task { await finish() } }
                }
            }
        } else if state == .failed || state == .stopped, mine, !e.isPhoneApp {
            GhostButton(title: "Try again") { ended = nil; running = true }
        }
        if (state == .waitingApproval || state == .planning || state == .needsYou), mine || guardian {
            Button(role: .destructive) { confirmCancel = true } label: { Text("Cancel the errand").font(Theme.font(14, .semibold)).frame(maxWidth: .infinity) }
                .buttonStyle(.bordered).tint(Theme.danger).disabled(busy)
        }

        // What happened, step by step. Only what the server wrote down.
        let steps = e.steps
        if !steps.isEmpty {
            SectionLabel(title: "What happened")
            ListCard {
                ForEach(Array(steps.enumerated()), id: \.element.id) { i, s in
                    HStack(alignment: .top, spacing: Spacing.m) {
                        VStack(spacing: 0) {
                            Circle().fill(i == steps.count - 1 ? state.tint : Theme.ink3).frame(width: 8, height: 8).padding(.top, 6)
                            if i < steps.count - 1 { Rectangle().fill(Theme.line).frame(width: 1).frame(maxHeight: .infinity) }
                        }.frame(width: 8)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(s.said).font(Theme.font(14)).foregroundStyle(Theme.ink)
                            if let at = s.at { Text(Format.stamp.string(from: at)).font(Theme.font(11)).foregroundStyle(Theme.ink3) }
                            if let pic = s.artifactId {
                                NavigationLink(value: pic) { Thumb(id: pic).frame(width: 150, height: 150).clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous)).overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(Theme.line, lineWidth: 0.5)) }
                                    .buttonStyle(.plain).accessibilityLabel("Picture of step \(i + 1)")
                            }
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(Spacing.s)
                    .accessibilityElement(children: .combine)
                }
            }
        }
        if let shared = e.outcome?["shared"], case .string(let s) = shared, let id = UUID(uuidString: s) {
            NavigationLink(value: id) { TaskRow(symbol: "doc.text", tint: Theme.success, title: "What it handed in", detail: "A private notice, read like any other") }
                .buttonStyle(.plain).background(Theme.card).clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        }
    }

    /// The site or app by its name, not its key.
    private func serviceLabel(_ e: Errand) -> String {
        e.appLabel ?? e.spec("where", "label") ?? ["urbancompany": "Urban Company", "myclassboard": "MyClassBoard school app", "iossettings": "iOS Settings", "swiggy": "Swiggy", "instamart": "Instamart"][e.service] ?? e.service
    }

    private func explain(_ e: Errand) -> String {
        switch state {
        case .waitingApproval: return "Written down in full and fingerprinted. Nothing runs until a guardian approves exactly this."
        case .planning: return "Approved. It starts when a phone picks it up" + (e.isPhoneApp ? " through the driver." : ", or from the console.")
        case .working: return "Running now. Every change it makes is written down before it happens."
        case .needsYou: return "It stopped where a person must look: the page it reached is kept."
        case .done: return "Finished" + (e.endedAt.map { " " + Format.stamp.string(from: $0) } ?? "") + "."
        case .failed: return "It could not finish. Nothing was paid."
        case .stopped: return "Stopped by a rule before anything was committed."
        case .cancelled: return "Cancelled. It did not run."
        case .suggested: return ""
        }
    }

    private func approvalLines(_ e: Errand) -> [ApprovalSummary.Line] {
        var out: [ApprovalSummary.Line] = [.init(label: "What", value: e.what)]
        if let d = e.spec("details") { out.append(.init(label: "Details", value: d)) }
        if let on = e.spec("when", "date") {
            let day = API.parseDate(on).map { Format.day.string(from: $0) + " " + String(Calendar.current.component(.year, from: $0)) } ?? on
            out.append(.init(label: "When", value: [day, e.spec("when", "time").map(Format.clockText), e.spec("when", "part").flatMap { $0 == "any" ? nil : $0 }].compactMap { $0 }.joined(separator: ", ")))
        }
        out.append(.init(label: "Where", value: serviceLabel(e) + (e.isPhoneApp ? ", on the phone" : "")))
        if e.kind != "look", let limit = e.spec("limits", "max_amount"), let amount = Double(limit) {
            out.append(.init(label: "At most", value: Format.money(amount, e.spec("limits", "currency") ?? "INR")))
            out.append(.init(label: "Payment", value: (e.spec("payment", "mode") ?? "").replacingOccurrences(of: "_", with: " ")))
        } else {
            out.append(.init(label: "Payment", value: "none; a look buys nothing"))
        }
        return out
    }

    private func load() async {
        do { errand = try await API.shared.errand(errandId); error = nil } catch { self.error = error.localizedDescription }
    }
    private func approve(sha: String) async {
        busy = true; defer { busy = false }
        do {
            errand = try await API.shared.approveErrand(errandId, sha: sha, onPhone: true); ended = nil
            if !(errand?.isPhoneApp ?? false) { running = true }
        } catch { self.error = error.localizedDescription }
    }
    private func finish() async {
        do { errand = try await API.shared.finishErrand(errandId) } catch { self.error = error.localizedDescription }
    }
    private func cancel() async {
        busy = true; defer { busy = false }
        do { errand = try await API.shared.cancelErrand(errandId); error = nil } catch { self.error = error.localizedDescription }
    }
}

/// The web view the runbook drives, and the socket it answers on.
struct PhoneBrowser: UIViewRepresentable {
    let errandId: UUID
    let onEnded: (String) -> Void

    func makeCoordinator() -> Bridge { Bridge(errandId: errandId, onEnded: onEnded) }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        // The phone's web view says what it is, on the family's own address: the
        // same token the server's browsers carry (familyos/execution/agent.py).
        configuration.applicationNameForUserAgent = "FamilyOS/0.2 (+household agent; each run approved by a guardian; never pays)"
        let web = WKWebView(frame: .zero, configuration: configuration)
        web.allowsBackForwardNavigationGestures = true
        context.coordinator.web = web
        context.coordinator.connect()
        return web
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    static func dismantleUIView(_ uiView: WKWebView, coordinator: Bridge) { coordinator.close() }

    /// Answers the server's questions with JavaScript in the page.
    final class Bridge: NSObject {
        let errandId: UUID
        let onEnded: (String) -> Void
        weak var web: WKWebView?
        var task: URLSessionWebSocketTask?

        init(errandId: UUID, onEnded: @escaping (String) -> Void) { self.errandId = errandId; self.onEnded = onEnded }

        func connect() {
            guard let url = API.shared.phoneSocketURL(errandId) else { onEnded("Not signed in."); return }
            let t = URLSession.shared.webSocketTask(with: url)
            task = t
            t.resume()
            receive()
        }

        func close() { task?.cancel(with: .normalClosure, reason: nil); task = nil }

        private func receive() {
            task?.receive { [weak self] result in
                guard let self else { return }
                switch result {
                case .failure(let err):
                    DispatchQueue.main.async { self.onEnded("The connection ended: \(err.localizedDescription)") }
                case .success(let message):
                    if case .string(let text) = message, let data = text.data(using: .utf8),
                       let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                        DispatchQueue.main.async { self.handle(obj) }
                    }
                    self.receive()
                }
            }
        }

        private func reply(_ id: String, _ result: Any?) {
            var obj: [String: Any] = ["id": id]
            obj["result"] = result ?? NSNull()
            if let data = try? JSONSerialization.data(withJSONObject: obj), let text = String(data: data, encoding: .utf8) {
                task?.send(.string(text)) { _ in }
            }
        }

        private func handle(_ m: [String: Any]) {
            let op = m["op"] as? String ?? ""
            if op == "ended" {
                let outcome = m["outcome"] as? [String: Any]
                let status = outcome?["status"] as? String
                let said = m["error"] as? String ?? (status == "needs_you" ? "It got this far and needs you. Finish on the page, then mark it done." : status == "done" ? "Done." : "Ended: \(status ?? "?")")
                onEnded(said); return
            }
            guard let id = m["id"] as? String, let web else { return }
            switch op {
            case "goto":
                if let s = m["url"] as? String, let u = URL(string: s) { web.load(URLRequest(url: u)) }
                DispatchQueue.main.asyncAfter(deadline: .now() + 3) { self.reply(id, nil) }
            case "url":
                reply(id, web.url?.absoluteString ?? "")
            case "text":
                web.evaluateJavaScript("(document.body && document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 6000)") { r, _ in self.reply(id, r as? String ?? "") }
            case "screenshot":
                let cfg = WKSnapshotConfiguration(); cfg.afterScreenUpdates = true
                web.takeSnapshot(with: cfg) { image, _ in
                    self.reply(id, image?.jpegData(compressionQuality: 0.55)?.base64EncodedString() ?? "")
                }
            case "buttons":
                let label = (m["label"] as? String ?? "").replacingOccurrences(of: "'", with: "\\'")
                web.evaluateJavaScript(Bridge.buttonsJS(label)) { r, _ in self.reply(id, r ?? []) }
            case "links":
                web.evaluateJavaScript(Bridge.linksJS) { r, _ in self.reply(id, r ?? []) }
            case "press":
                let label = (m["label"] as? String ?? "").replacingOccurrences(of: "'", with: "\\'")
                let index = m["index"] as? Int ?? 0
                web.evaluateJavaScript(Bridge.pressJS(label, index)) { r, _ in
                    DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) { self.reply(id, (r as? Bool) ?? false) }
                }
            case "click_text":
                let text = (m["text"] as? String ?? "").replacingOccurrences(of: "'", with: "\\'")
                web.evaluateJavaScript(Bridge.clickTextJS(text)) { r, _ in
                    DispatchQueue.main.asyncAfter(deadline: .now() + 3) { self.reply(id, (r as? Bool) ?? false) }
                }
            case "close":
                reply(id, nil)
            default:
                reply(id, nil)
            }
        }

        // The same scripts the server's own driver runs in Chromium.
        static let near = "function near(b){let box=b,fallback=null;for(let i=0;i<10&&box.parentElement;i++){box=box.parentElement;const t=(box.innerText||'').replace(/\\s+/g,' ').trim();if(!fallback&&t.length>40)fallback=box;if(/₹\\s?[\\d,]+/.test(t)&&t.length<400)return t.slice(0,160);}return ((fallback||b).innerText||'').replace(/\\s+/g,' ').trim().slice(0,160);}"
        static func buttonsJS(_ label: String) -> String {
            "(function(){\(near) const re=new RegExp('^\\\\s*'+'\(label)'.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&')+'\\\\s*$','i'); const out=[]; let i=0; for(const b of document.querySelectorAll('button')){ if(!re.test(b.innerText||'')) continue; out.push({index:i++, near:near(b)}); if(out.length>=30) break;} return out;})()"
        }
        static let linksJS = "(function(){const seen=new Set();const out=[];for(const a of document.querySelectorAll('a[href]')){const t=(a.innerText||'').replace(/\\s+/g,' ').trim();const h=a.href;if(!t||t.length>80||!h.startsWith('https://')||seen.has(h))continue;seen.add(h);out.push({text:t,href:h});if(out.length>=60)break;}return out;})()"
        static func pressJS(_ label: String, _ index: Int) -> String {
            "(function(){const re=new RegExp('^\\\\s*'+'\(label)'.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&')+'\\\\s*$','i'); const hits=[...document.querySelectorAll('button')].filter(b=>re.test(b.innerText||'')); const b=hits[\(index)]; if(!b) return false; b.scrollIntoView({block:'center'}); b.click(); return true;})()"
        }
        static func clickTextJS(_ text: String) -> String {
            "(function(){const want='\(text)'.toLowerCase(); const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_ELEMENT); let n; while((n=walker.nextNode())){ if(n.children.length>3) continue; const t=(n.innerText||'').trim().toLowerCase(); if(t&&t.includes(want)&&t.length<200){ n.scrollIntoView({block:'center'}); n.click(); return true; } } return false;})()"
        }
    }
}
