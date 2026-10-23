// The phone's own hands: an XCTest runner that drives apps on this iPhone
// for FamilyOS. Launched once from the Mac (xcodebuild test), it holds a
// socket to the server and answers the same questions the web view
// answers, with the accessibility tree instead of the DOM: open an app,
// what does the screen say, which buttons say Add, press the second one.
// Developer-signed, Developer Mode on: a household that builds its own
// phone, never the store. Every tap is a commit mark on the server side.
import XCTest

final class DriverTests: XCTestCase {
    func testDrive() throws {
        // An app that will not open is an answer to send back, not the end
        // of the run: XCTest records the failure and the bridge carries on.
        continueAfterFailure = true
        let env = ProcessInfo.processInfo.environment
        guard let socket = env["FAMILYOS_SOCKET"], let url = URL(string: socket) else {
            throw XCTSkip("set FAMILYOS_SOCKET to wss://server/v1/errands/<id>/phone?token=<session token>")
        }
        let bridge = Bridge(url: url)
        bridge.connect()
        let deadline = Date().addingTimeInterval(TimeInterval(env["FAMILYOS_MINUTES"].flatMap(Double.init) ?? 20) * 60)
        while !bridge.ended && Date() < deadline {
            RunLoop.current.run(until: Date().addingTimeInterval(0.25))
            bridge.pump()
        }
        XCTAssertTrue(bridge.ended, "the run did not end before the time allowed")
    }
}

/// Answers the server's questions with XCUITest.
final class Bridge: NSObject {
    let url: URL
    var task: URLSessionWebSocketTask?
    var ended = false
    private var app: XCUIApplication?
    private let lock = NSLock()
    private var inbox: [[String: Any]] = []

    init(url: URL) { self.url = url }

    func connect() {
        let t = URLSession(configuration: .default).webSocketTask(with: url)
        task = t
        t.resume()
        receive()
    }

    private func receive() {
        task?.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .failure: self.ended = true
            case .success(let message):
                if case .string(let text) = message, let data = text.data(using: .utf8),
                   let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    self.lock.lock(); self.inbox.append(obj); self.lock.unlock()
                }
                self.receive()
            }
        }
    }

    /// Questions are answered on the test's own thread, where XCUITest lives.
    func pump() {
        lock.lock(); let batch = inbox; inbox.removeAll(); lock.unlock()
        for m in batch { handle(m) }
    }

    private func reply(_ id: String, _ result: Any?, error: String? = nil) {
        var obj: [String: Any] = ["id": id]
        obj["result"] = result ?? NSNull()
        if let error { obj["error"] = error }
        if let data = try? JSONSerialization.data(withJSONObject: obj), let text = String(data: data, encoding: .utf8) {
            task?.send(.string(text)) { _ in }
        }
    }

    private func handle(_ m: [String: Any]) {
        let op = m["op"] as? String ?? ""
        if op == "ended" { ended = true; return }
        guard let id = m["id"] as? String else { return }
        switch op {
        case "open":
            let bundle = m["bundle"] as? String ?? m["url"] as? String ?? ""
            let a = XCUIApplication(bundleIdentifier: bundle)
            a.activate()
            if a.wait(for: .runningForeground, timeout: 10) {
                app = a
                sleep(2)   // a splash, a web view, a list still loading
                reply(id, bundle)
            } else {
                reply(id, nil, error: "the app \(bundle) is not on this phone, or did not open")
            }
        case "goto":
            // A URL on the phone opens in whatever app owns it; a web page in Safari.
            if let s = m["url"] as? String, let u = URL(string: s) {
                let safari = XCUIApplication(bundleIdentifier: "com.apple.mobilesafari")
                safari.open(u)
                app = safari
                _ = safari.wait(for: .runningForeground, timeout: 10)
                sleep(3)
            }
            reply(id, nil)
        case "url":
            reply(id, app?.label ?? "")
        case "text":
            reply(id, screenText())
        case "screenshot":
            let png = XCUIScreen.main.screenshot().pngRepresentation
            let jpeg = UIImage(data: png)?.jpegData(compressionQuality: 0.5) ?? png
            reply(id, jpeg.base64EncodedString())
        case "buttons":
            let label = m["label"] as? String ?? ""
            reply(id, buttons(label))
        case "links":
            reply(id, [])
        case "press":
            let label = m["label"] as? String ?? ""
            let index = m["index"] as? Int ?? 0
            reply(id, press(label, index))
        case "click_text":
            let text = m["text"] as? String ?? ""
            reply(id, tap(containing: text))
        case "swipe":
            // One screen of a list, in the direction said; the picture after
            // it is the next page.
            let direction = m["direction"] as? String ?? "up"
            if let app {
                if direction == "down" { app.swipeDown() } else { app.swipeUp() }
                sleep(1)
                reply(id, true)
            } else {
                reply(id, false)
            }
        case "close":
            reply(id, nil)
        default:
            reply(id, nil, error: "unknown op \(op)")
        }
    }

    // MARK: the screen as words

    private func screenText() -> String {
        guard let app else { return "" }
        var out: [String] = []
        let q = app.descendants(matching: .any)
        let n = min(q.count, 400)
        for i in 0..<n {
            let e = q.element(boundBy: i)
            guard e.exists, e.isHittable || e.elementType == .staticText else { continue }
            let label = e.label.trimmingCharacters(in: .whitespacesAndNewlines)
            let value = (e.value as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if !label.isEmpty { out.append(label) }
            if !value.isEmpty && value != label { out.append(value) }
        }
        var seen = Set<String>()
        return out.filter { seen.insert($0).inserted }.joined(separator: " · ").prefix(6000).description
    }

    private func buttons(_ label: String) -> [[String: Any]] {
        guard let app else { return [] }
        let want = label.lowercased()
        let q = app.buttons
        var out: [[String: Any]] = []
        for i in 0..<min(q.count, 60) {
            let b = q.element(boundBy: i)
            guard b.exists, b.label.trimmingCharacters(in: .whitespaces).lowercased() == want else { continue }
            out.append(["index": out.count, "near": near(b)])
            if out.count >= 30 { break }
        }
        return out
    }

    /// The words around a button: its cell's labels, the way the web driver
    /// takes the card around an Add.
    private func near(_ b: XCUIElement) -> String {
        guard let app else { return b.label }
        let cells = app.cells.containing(.button, identifier: b.identifier.isEmpty ? b.label : b.identifier)
        if cells.count > 0 {
            let cell = cells.element(boundBy: 0)
            let labels = cell.staticTexts.allElementsBoundByIndex.map(\.label).filter { !$0.isEmpty }
            if !labels.isEmpty { return labels.joined(separator: " ").prefix(160).description }
        }
        return b.label
    }

    private func press(_ label: String, _ index: Int) -> Bool {
        guard let app else { return false }
        let want = label.lowercased()
        var n = 0
        let q = app.buttons
        for i in 0..<min(q.count, 60) {
            let b = q.element(boundBy: i)
            guard b.exists, b.label.trimmingCharacters(in: .whitespaces).lowercased() == want else { continue }
            if n == index { b.tap(); sleep(2); return true }
            n += 1
        }
        return false
    }

    private func tap(containing text: String) -> Bool {
        guard let app else { return false }
        let want = text.lowercased()
        for kind: XCUIElement.ElementType in [.button, .cell, .staticText, .link, .other] {
            let q = app.descendants(matching: kind)
            for i in 0..<min(q.count, 200) {
                let e = q.element(boundBy: i)
                guard e.exists, e.isHittable, e.label.lowercased().contains(want) else { continue }
                e.tap(); sleep(3); return true
            }
        }
        return false
    }
}
