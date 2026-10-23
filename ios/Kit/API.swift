// The API client: one URLSession, bearer token, snake_case JSON, the three
// date shapes the server sends. Every call the app makes is a method here,
// named after the route it hits.
import Foundation

public struct APIError: LocalizedError {
    public let status: Int
    public let detail: String
    public var errorDescription: String? { detail }
}

public final class API {
    public static let shared = API()

    public static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        d.dateDecodingStrategy = .custom { decoder in
            let s = try decoder.singleValueContainer().decode(String.self)
            if let date = API.parseDate(s) { return date }
            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "unreadable date \(s)"))
        }
        return d
    }()

    public static let encoder: JSONEncoder = {
        let e = JSONEncoder()
        e.keyEncodingStrategy = .convertToSnakeCase
        // Dates the app sends are days (a to-do's due date), never instants.
        e.dateEncodingStrategy = .custom { date, enc in var c = enc.singleValueContainer(); try c.encode(API.dayOnly.string(from: date)) }
        return e
    }()

    private static let isoFraction: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]; return f
    }()
    private static let iso: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime]; return f
    }()
    static let dayOnly: DateFormatter = {
        let f = DateFormatter(); f.calendar = Calendar(identifier: .iso8601); f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = .current; f.dateFormat = "yyyy-MM-dd"; return f
    }()

    static func parseDate(_ s: String) -> Date? {
        // A datetime with or without fractional seconds and an offset, or a date.
        if let d = isoFraction.date(from: s) ?? iso.date(from: s) { return d }
        let naive = s.contains("+") || s.hasSuffix("Z") ? s : s + "Z"
        if let d = isoFraction.date(from: naive) ?? iso.date(from: naive) { return d }
        return dayOnly.date(from: String(s.prefix(10)))
    }

    private let session: URLSession = {
        let c = URLSessionConfiguration.default
        c.timeoutIntervalForRequest = 60
        c.waitsForConnectivity = true
        return URLSession(configuration: c)
    }()

    private init() {}

    // MARK: plumbing

    public enum Auth { case session, device }

    func url(_ path: String, query: [String: String] = [:]) throws -> URL {
        guard let base = Server.baseURL else { throw APIError(status: 0, detail: "No server address yet.") }
        var comps = URLComponents(url: base.appendingPathComponent("v1" + path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty { comps.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) } }
        return comps.url!
    }

    func send(_ method: String, _ path: String, query: [String: String] = [:], body: Data? = nil,
              contentType: String? = nil, headers: [String: String] = [:], auth: Auth = .session,
              signed: Bool = true, requestId: String? = nil) async throws -> (Data, HTTPURLResponse) {
        var req = URLRequest(url: try url(path, query: query))
        req.httpMethod = method
        if signed {
            let token = auth == .device ? (Server.deviceToken ?? Server.token) : Server.token
            guard let token else { throw APIError(status: 401, detail: "Not signed in.") }
            req.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        }
        if let body {
            req.httpBody = body
            req.setValue(contentType ?? "application/json", forHTTPHeaderField: "Content-Type")
        }
        for (k, v) in headers { req.setValue(v, forHTTPHeaderField: k) }
        if let requestId { req.setValue(requestId, forHTTPHeaderField: "X-Request-Id") }
        let (data, resp) = try await session.data(for: req)
        let http = resp as? HTTPURLResponse ?? HTTPURLResponse(url: req.url!, statusCode: 0, httpVersion: nil, headerFields: nil)!
        guard (200..<300).contains(http.statusCode) else {
            throw APIError(status: http.statusCode, detail: API.detail(from: data, status: http.statusCode))
        }
        return (data, http)
    }

    func json<T: Decodable>(_ method: String, _ path: String, query: [String: String] = [:],
                            body: (any Encodable)? = nil, signed: Bool = true, requestId: String? = nil) async throws -> T {
        let data = try body.map { try API.encoder.encode(AnyEncodable($0)) }
        let (out, _) = try await send(method, path, query: query, body: data, signed: signed, requestId: requestId)
        do { return try API.decoder.decode(T.self, from: out) }
        catch { throw APIError(status: 0, detail: "The server's answer could not be read: \(error)") }
    }

    static func detail(from data: Data, status: Int) -> String {
        if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            if let s = obj["detail"] as? String { return s }
            if let s = obj["message"] as? String { return s }
            if let arr = obj["detail"] as? [[String: Any]], let first = arr.first, let msg = first["msg"] as? String { return msg }
        }
        switch status {
        case 401: return "Sign in again."
        case 403: return "Not allowed for this member."
        case 404: return "Not found."
        default: return "The server answered \(status)."
        }
    }

    // MARK: sign-in

    public func requestSignIn(email: String) async throws {
        _ = try await send("POST", "/sign-in/request", body: try API.encoder.encode(["email": email]), signed: false)
    }

    public func redeem(link: String) async throws -> SignedIn {
        try await json("POST", "/sign-in/redeem", body: ["link": link], signed: false)
    }

    public func signOut() async throws { _ = try await send("POST", "/signout") }

    /// Where to send someone who chose Continue with Google, begun for the
    /// app: the callback returns on familyos://signed-in with the token.
    public func googleSignInURL() async throws -> URL {
        let out: GoogleSignIn = try await json("GET", "/sign-in/google", query: ["native": "true"], signed: false)
        guard let url = URL(string: out.url) else { throw APIError(status: 0, detail: "Google gave no address to open.") }
        return url
    }

    /// A token that arrived whole (Google's callback): keep it and ask who it is.
    public func signIn(token: String) async throws -> SignedIn {
        let before = Server.token
        Server.token = token
        do { return SignedIn(member: try await me(), token: token) }
        catch { Server.token = before; throw error }
    }

    public func me() async throws -> Member { try await json("GET", "/me") }
    public func household() async throws -> Household { try await json("GET", "/household") }

    // MARK: reading

    public func brief() async throws -> Brief { try await json("GET", "/brief") }
    public func inbox(days: Int = 60, limit: Int = 200) async throws -> [InboxRow] {
        try await json("GET", "/inbox", query: ["days": String(days), "limit": String(limit)])
    }
    public func artifact(_ id: UUID) async throws -> Artifact { try await json("GET", "/artifacts/\(id.uuidString)") }
    public func extraction(_ id: UUID) async throws -> ArtifactExtraction { try await json("GET", "/artifacts/\(id.uuidString)/extraction") }
    public func obligations(status: String? = nil) async throws -> [Obligation] {
        try await json("GET", "/obligations", query: ["status": status ?? "", "limit": "500"])
    }
    public func picture(_ id: UUID) async throws -> Data { try await send("GET", "/artifacts/\(id.uuidString)/picture").0 }
    public func original(_ id: UUID) async throws -> (Data, String) {
        let (data, http) = try await send("GET", "/artifacts/\(id.uuidString)/original")
        return (data, http.value(forHTTPHeaderField: "Content-Type") ?? "application/octet-stream")
    }

    public func money(days: Int = 120) async throws -> Money { try await json("GET", "/money", query: ["days": String(days)]) }
    public func plans() async throws -> [Plan] { try await json("GET", "/plans") }
    public func errands() async throws -> [Errand] { try await json("GET", "/errands") }
    public func errand(_ id: UUID) async throws -> Errand { try await json("GET", "/errands/\(id.uuidString)") }
    public func approveErrand(_ id: UUID, sha: String, onPhone: Bool) async throws -> Errand {
        try await json("POST", "/errands/\(id.uuidString)/approve", body: ApproveBody(paramsSha256: sha, runOn: onPhone ? "phone" : nil))
    }
    public func finishErrand(_ id: UUID) async throws -> Errand { try await json("POST", "/errands/\(id.uuidString)/finish") }
    public func cancelErrand(_ id: UUID) async throws -> Errand { try await json("POST", "/errands/\(id.uuidString)/cancel") }
    /// A proposal from Ask written down as an errand: nothing runs until a
    /// guardian approves exactly this. A look needs no limit; a booking does.
    public func proposeErrand(service: String, look: Bool, title: String, what: String, details: String?, dueDate: Date?, dueTime: String?, part: String?,
                              maxAmount: Double?, currency: String?, bundle: String? = nil) async throws -> Errand {
        try await json("POST", "/errands", body: ErrandBody(service: service, kind: look ? "look" : "booking", title: title,
                                                            spec: ErrandSpecBody(what: what, details: details, when: ErrandWhenBody(date: dueDate, time: dueTime, part: part ?? "any"),
                                                                                 maxAmount: maxAmount, currency: currency ?? "INR", payment: "pay_after_service", bundle: bundle)))
    }
    /// The socket the phone holds open while it is the errand's browser.
    public func phoneSocketURL(_ id: UUID) -> URL? {
        guard let base = Server.baseURL, let token = Server.token else { return nil }
        var c = URLComponents(url: base.appendingPathComponent("v1/errands/\(id.uuidString)/phone"), resolvingAgainstBaseURL: false)!
        c.scheme = base.scheme == "https" ? "wss" : "ws"
        c.queryItems = [URLQueryItem(name: "token", value: token)]
        return c.url
    }
    public func calendarUpcoming(days: Int = 7) async throws -> [CalendarEvent] {
        try await json("GET", "/calendar/upcoming", query: ["days": String(days)])
    }

    public func artifacts(limit: Int = 200) async throws -> [Artifact] { try await json("GET", "/artifacts", query: ["limit": String(limit)]) }
    public func todos() async throws -> [Todo] { try await json("GET", "/todos") }

    // MARK: offers
    public func offers() async throws -> [Offer] { try await json("GET", "/offers") }
    public func acceptOffer(_ key: String) async throws -> OfferDone {
        try await json("POST", "/offers/\(key.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? key)/accept")
    }
    public func dismissOffer(_ key: String) async throws {
        _ = try await send("POST", "/offers/\(key.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? key)/dismiss")
    }
    public func documents() async throws -> Documents { try await json("GET", "/documents") }

    // MARK: chat

    public func chat(_ message: String, history: [ChatMessage]) async throws -> ChatTurn {
        try await json("POST", "/chat", body: ChatBody(message: message, history: history))
    }

    /// The answer as it is written: say deltas, then the finished turn, as
    /// newline-delimited JSON from /chat/stream. A server without the route
    /// yields the whole turn at once.
    public enum ChatEvent { case say(String); case turn(ChatTurn) }
    public func chatStream(_ message: String, history: [ChatMessage]) -> AsyncThrowingStream<ChatEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    var req = URLRequest(url: try url("/chat/stream"))
                    req.httpMethod = "POST"
                    guard let token = Server.token else { throw APIError(status: 401, detail: "Not signed in.") }
                    req.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
                    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    req.httpBody = try API.encoder.encode(ChatBody(message: message, history: history))
                    let (bytes, resp) = try await session.bytes(for: req)
                    guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                        let whole = try await chat(message, history: history)
                        continuation.yield(.say(whole.say)); continuation.yield(.turn(whole)); continuation.finish(); return
                    }
                    var said = ""; var finished = false
                    for try await line in bytes.lines {
                        guard let data = line.data(using: .utf8), let ev = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let type = ev["type"] as? String else { continue }
                        if type == "say", let delta = ev["delta"] as? String { said += delta; continuation.yield(.say(said)) }
                        else if type == "turn" { continuation.yield(.turn(try API.decoder.decode(ChatTurn.self, from: data))); finished = true }
                        else if type == "error" { throw APIError(status: 502, detail: (ev["detail"] as? String) ?? "The model did not answer.") }
                    }
                    if !finished { throw APIError(status: 502, detail: "The answer stopped before it was finished.") }
                    continuation.finish()
                } catch { continuation.finish(throwing: error) }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
    public func addTodo(title: String, dueDate: Date?, dueTime: String?, assignedTo: UUID?, note: String?) async throws -> Todo {
        try await json("POST", "/todos", body: TodoBody(title: title, dueDate: dueDate, dueTime: dueTime, assignedTo: assignedTo, note: note))
    }
    public func setTodoDone(_ id: UUID, _ done: Bool) async throws -> Todo {
        try await json("PATCH", "/todos/\(id.uuidString)", body: ["done": done])
    }
    public func draftPlan(brief: String, shape: String) async throws -> Plan {
        try await json("POST", "/plans", body: PlanBody(brief: brief, shape: shape))
    }

    // MARK: deciding

    public func decide(_ obligation: UUID, _ status: String, requestId: String? = nil) async throws -> Obligation {
        try await json("POST", "/obligations/\(obligation.uuidString)/decision", body: ["status": status], requestId: requestId)
    }
    public func handled(_ artifact: UUID, note: String?, requestId: String? = nil) async throws -> Handled {
        try await json("POST", "/artifacts/\(artifact.uuidString)/handled", body: ["note": note], requestId: requestId)
    }
    public func reopen(_ artifact: UUID) async throws -> Handled { try await json("DELETE", "/artifacts/\(artifact.uuidString)/handled") }
    public func assign(_ artifact: UUID, to member: UUID?, note: String?, requestId: String? = nil) async throws -> Assigned {
        try await json("POST", "/artifacts/\(artifact.uuidString)/assign", body: AssignBody(memberId: member, note: note), requestId: requestId)
    }

    // MARK: asking

    public func ask(_ question: String) async throws -> Answer { try await json("POST", "/ask", body: ["question": question]) }

    // MARK: devices

    public func devices() async throws -> [Device] { try await json("GET", "/devices") }
    /// A one-time deep link that binds this member's Telegram to the bot.
    public func telegramLink() async throws -> TelegramLink { try await json("POST", "/telegram/link") }
    public func addDevice(label: String) async throws -> DeviceIssued { try await json("POST", "/devices", body: ["label": label]) }
    public func revokeDevice(_ id: UUID) async throws { _ = try await send("DELETE", "/devices/\(id.uuidString)") }

    // MARK: sharing (the share extension's one call)

    /// The raw-body shape the share route takes: the thing itself as the body,
    /// the tag, note and visibility as headers. The same request the share
    /// shortcut makes, minus the shortcut.
    public func share(data: Data, contentType: String, tag: String?, note: String?, shared: Bool, requestId: String? = nil) async throws -> ShareResult {
        var headers = ["X-Visibility": shared ? "shared" : "private"]
        if let tag, !tag.isEmpty { headers["X-Tag"] = tag }
        if let note, !note.isEmpty { headers["X-Note"] = note }
        let (out, _) = try await send("POST", "/inbound/share", body: data, contentType: contentType, headers: headers, auth: .device, requestId: requestId)
        return try API.decoder.decode(ShareResult.self, from: out)
    }
}

struct AssignBody: Encodable { let memberId: UUID?; let note: String? }
struct ApproveBody: Encodable { let paramsSha256: String; let runOn: String? }

struct AnyEncodable: Encodable {
    let value: any Encodable
    init(_ value: any Encodable) { self.value = value }
    func encode(to encoder: Encoder) throws { try value.encode(to: encoder) }
}
