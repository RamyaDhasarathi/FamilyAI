import SwiftUI

/// The first screen, once: what FamilyOS does, how things reach it, and
/// what it never does. Three short pages and a way in. No permission is
/// asked here; each is asked where it is used, with the reason beside it.
struct WelcomeView: View {
    let done: () -> Void
    @State private var page = 0
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private struct Page: Identifiable { let id: Int; let symbol: String; let tint: Color; let title: String; let text: String }
    private let pages = [
        Page(id: 0, symbol: "sparkle", tint: Theme.primary, title: "One place for the family's\nnotices, dates and bills.",
             text: "School circulars, bills, receipts and plans, read for what they ask of you. The day's brief, what needs a decision, and who is handling what."),
        Page(id: 1, symbol: "square.and.arrow.up", tint: Space.school.color, title: "Share anything to it.",
             text: "A screenshot, a WhatsApp forward, a PDF, a photo of a form: share it from any app and FamilyOS reads it. Mail can be forwarded to the household's own address."),
        Page(id: 2, symbol: "hand.raised", tint: Theme.success, title: "It proposes. You decide.",
             text: "Dates and errands are proposed, never done behind your back. Every action shows exactly what it will do first. It never holds a card or a password, and never pays."),
    ]

    var body: some View {
        VStack(spacing: 0) {
            TabView(selection: $page) {
                ForEach(pages) { p in
                    VStack(spacing: Spacing.xl) {
                        Spacer()
                        Image(systemName: p.symbol).font(.system(size: 44, weight: .medium)).foregroundStyle(p.tint)
                            .frame(width: 96, height: 96).background(p.tint.opacity(0.12)).clipShape(Circle())
                            .accessibilityHidden(true)
                        VStack(spacing: Spacing.m) {
                            Text(p.title).font(Theme.font(28, .regular, .serif)).foregroundStyle(Theme.ink).multilineTextAlignment(.center)
                            Text(p.text).font(Theme.font(16)).foregroundStyle(Theme.ink2).multilineTextAlignment(.center).lineSpacing(3)
                        }
                        Spacer()
                        Spacer()
                    }
                    .padding(.horizontal, Spacing.xl)
                    .tag(p.id)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .always))
            .indexViewStyle(.page(backgroundDisplayMode: .never))
            .animation(Motion.gentle(reduceMotion), value: page)

            VStack(spacing: Spacing.m) {
                PrimaryButton(title: page < pages.count - 1 ? "Continue" : "Get started") {
                    if page < pages.count - 1 { withAnimation(Motion.gentle(reduceMotion)) { page += 1 } } else { done() }
                }
                Button("Skip") { done() }.font(Theme.font(15, .medium)).foregroundStyle(Theme.ink3).opacity(page < pages.count - 1 ? 1 : 0)
                    .accessibilityHidden(page == pages.count - 1)
                Text("Start on your own. Invite the family from the console once you have seen it work.").font(Theme.font(12)).foregroundStyle(Theme.ink3).multilineTextAlignment(.center)
            }
            .padding(.horizontal, Spacing.xl).padding(.bottom, Spacing.xl)
        }
        .paper()
        .sensoryFeedback(.selection, trigger: page)
    }
}

#Preview("Welcome") { WelcomeView(done: {}) }
#Preview("Welcome · dark, large") { WelcomeView(done: {}).preferredColorScheme(.dark).environment(\.dynamicTypeSize, .accessibility2) }
