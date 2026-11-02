import SwiftUI

/// What needs you, as cards with the answer one tap away. The cards come from the server, so a card's words are the
/// staged action's own: a button runs exactly what the card says, as you, and nothing else.
struct OpeningCardsView: View {
    let opening: ChatOpening
    @State private var gone: Set<String> = []
    @State private var said: String?
    @State private var failure: String?

    private var shown: [OpeningCard] { opening.cards.filter { $0.type != "chips" && !gone.contains($0.id) } }

    var body: some View {
        if !shown.isEmpty {
            VStack(alignment: .leading, spacing: Spacing.s) {
                Text(opening.say).font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                ForEach(shown) { c in card(c) }
                if let said { Text(said).font(Theme.font(13)).foregroundStyle(Theme.green) }
                if let failure { Text(failure).font(Theme.font(13)).foregroundStyle(Theme.warning) }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder private func card(_ c: OpeningCard) -> some View {
        if c.type == "text", let t = c.text {
            Text(t).font(Theme.font(13)).foregroundStyle(Theme.ink3)
        } else if c.type == "action" {
            Card(padding: 12) {
                VStack(alignment: .leading, spacing: 8) {
                    Text(c.title ?? "").font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                    if let sub = c.sub, !sub.isEmpty { Text(sub).font(Theme.font(12)).foregroundStyle(Theme.ink3) }
                    HStack(spacing: Spacing.s) {
                        ForEach(Array((c.buttons ?? []).enumerated()), id: \.offset) { i, b in button(b, first: i == 0, card: c) }
                        Spacer(minLength: 0)
                    }
                }
            }
        }
    }

    @ViewBuilder private func button(_ b: OpeningCard.Button, first: Bool, card: OpeningCard) -> some View {
        switch b.kind {
        case "link":
            if let u = b.url.flatMap(URL.init(string:)) { Link(b.label, destination: u).font(Theme.font(13, .semibold)) }
        default:
            if first {
                Button(b.label) { run(b, card) }.buttonStyle(.borderedProminent).tint(Theme.primary).controlSize(.small)
            } else {
                Button(b.label) { run(b, card) }.buttonStyle(.bordered).tint(Theme.ink2).controlSize(.small)
            }
        }
    }

    private func run(_ b: OpeningCard.Button, _ card: OpeningCard) {
        guard let id = b.id else { return }
        Task {
            do {
                if b.kind == "confirm" { said = try await API.shared.confirmPending(id) } else { try await API.shared.cancelPending(id); said = nil }
                failure = nil
                gone.insert(card.id)
            } catch { failure = error.localizedDescription }
        }
    }
}
