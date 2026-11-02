// Needs you, read one card at a time. The server keeps adding kinds of card
// (a heads-up, a document, a warranty, a waiting app); a card this build
// cannot read is left out rather than emptying the whole queue.
import Foundation

extension API {
    /// The queue and how many cards were left out.
    public func decisionsLossy() async throws -> (cards: [DecisionCard], skipped: Int) {
        let (data, _) = try await send("GET", "/decisions")
        let all = try API.decoder.decode([Lossy<DecisionCard>].self, from: data)
        let cards = all.compactMap(\.value)
        return (cards, all.count - cards.count)
    }
}

/// A value that is nil when it does not decode, so one odd element never sinks a list.
struct Lossy<T: Decodable>: Decodable {
    let value: T?
    init(from decoder: Decoder) throws { value = try? T(from: decoder) }
}
