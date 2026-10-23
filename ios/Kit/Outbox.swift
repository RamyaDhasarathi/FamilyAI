// What the phone could not send yet: a share from the sheet when the signal
// was gone, an Accept tapped on the train. Each is written to a file under
// the app group before anything else happens, with a request id, and
// replayed in order the next time the app or the extension runs and the
// server answers. The server already ignores a share it has by content hash
// and treats a decision made twice as made once, so a replay is safe.
import Foundation

public struct Pending: Codable, Identifiable {
    public enum Kind: String, Codable { case share, decide, handled, assign }
    public let id: String                 // the request id, sent as X-Request-Id
    public let kind: Kind
    public let at: Date
    public var file: String?              // a share's bytes, as a file in the outbox folder
    public var contentType: String?
    public var tag: String?
    public var note: String?
    public var shared: Bool?
    public var target: UUID?              // the obligation or artifact
    public var status: String?            // accepted / dismissed
    public var member: UUID?              // assign: to whom
    public var label: String              // one line for the person: what is waiting
}

public enum Outbox {
    static var folder: URL {
        let base = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: Server.appGroup)
            ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        let dir = base.appendingPathComponent("outbox", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }
    static var index: URL { folder.appendingPathComponent("pending.json") }

    public static func pending() -> [Pending] {
        guard let data = try? Data(contentsOf: index) else { return [] }
        return (try? API.decoder.decode([Pending].self, from: data)) ?? []
    }

    static func save(_ items: [Pending]) {
        try? (try? API.encoder.encode(items))?.write(to: index, options: .atomic)
    }

    /// Keep a share for later. The bytes go to their own file first.
    public static func keepShare(data: Data, contentType: String, tag: String?, note: String?, shared: Bool, label: String) {
        let id = UUID().uuidString
        let file = id + ".bin"
        guard (try? data.write(to: folder.appendingPathComponent(file), options: .atomic)) != nil else { return }
        var items = pending()
        items.append(Pending(id: id, kind: .share, at: Date(), file: file, contentType: contentType, tag: tag, note: note, shared: shared,
                             target: nil, status: nil, member: nil, label: label))
        save(items)
    }

    public static func keep(kind: Pending.Kind, target: UUID, status: String? = nil, member: UUID? = nil, note: String? = nil, label: String) {
        var items = pending()
        items.append(Pending(id: UUID().uuidString, kind: kind, at: Date(), file: nil, contentType: nil, tag: nil, note: note, shared: nil,
                             target: target, status: status, member: member, label: label))
        save(items)
    }

    /// Whether an error means "try again later" rather than "this is wrong".
    public static func isTransient(_ error: Error) -> Bool {
        if let api = error as? APIError { return api.status == 0 || api.status >= 500 || api.status == 408 || api.status == 429 }
        if let url = error as? URLError {
            return [.notConnectedToInternet, .timedOut, .cannotFindHost, .cannotConnectToHost, .networkConnectionLost, .dnsLookupFailed].contains(url.code)
        }
        return false
    }

    /// Send what is waiting, oldest first; stop at the first transient failure.
    /// A permanent refusal (a 4xx) drops the item: it will not get better.
    @discardableResult
    public static func replay() async -> (sent: Int, left: Int) {
        var items = pending()
        guard !items.isEmpty, Server.isSignedIn else { return (0, items.count) }
        var sent = 0
        while let item = items.first {
            do {
                try await send(item)
                if let file = item.file { try? FileManager.default.removeItem(at: folder.appendingPathComponent(file)) }
                items.removeFirst(); sent += 1; save(items)
            } catch {
                if isTransient(error) { break }
                if let file = item.file { try? FileManager.default.removeItem(at: folder.appendingPathComponent(file)) }
                items.removeFirst(); save(items)
            }
        }
        return (sent, items.count)
    }

    static func send(_ item: Pending) async throws {
        switch item.kind {
        case .share:
            guard let file = item.file, let data = try? Data(contentsOf: folder.appendingPathComponent(file)) else { return }
            _ = try await API.shared.share(data: data, contentType: item.contentType ?? "application/octet-stream", tag: item.tag, note: item.note,
                                           shared: item.shared ?? false, requestId: item.id)
        case .decide:
            guard let t = item.target, let s = item.status else { return }
            _ = try await API.shared.decide(t, s, requestId: item.id)
        case .handled:
            guard let t = item.target else { return }
            _ = try await API.shared.handled(t, note: item.note, requestId: item.id)
        case .assign:
            guard let t = item.target else { return }
            _ = try await API.shared.assign(t, to: item.member, note: item.note, requestId: item.id)
        }
    }
}
