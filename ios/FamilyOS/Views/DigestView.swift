import SwiftUI

/// This week's digest, as it would reach you, in the same words. "Send it to me now" sends it to you only, over Telegram or else email.
struct DigestView: View {
    @State private var digest: DigestPreview?
    @State private var error: String?
    @State private var sending = false
    @State private var sentNote: String?
    @State private var sentCount = 0
    private let isSample: Bool

    init() { isSample = false }
    init(sample: DigestPreview) { _digest = State(initialValue: sample); isSample = true }

    var body: some View {
        List {
            if digest == nil && error == nil { LoadingRows(count: 3).listRowBackground(Color.clear).listRowInsets(EdgeInsets()) }
            if let digest {
                Section {
                    Text(digest.subject).font(Theme.font(16, .semibold)).foregroundStyle(Theme.ink)
                    Text(digest.body).font(Theme.font(14)).foregroundStyle(Theme.ink2)
                } footer: { Text(digest.sendsOn) }
                Section {
                    Button { Task { await send() } } label: { Label(sending ? "Sending…" : "Send it to me now", systemImage: "paperplane") }.disabled(sending)
                } footer: { Text(sentNote ?? "Goes to you alone, only what you can see.") }
            }
            if let error { Text(error).font(Theme.font(13)).foregroundStyle(Theme.danger).listRowBackground(Color.clear) }
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
        .navigationTitle("Weekly digest")
        .navigationBarTitleDisplayMode(.inline)
        .sensoryFeedback(.success, trigger: sentCount)
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        guard !isSample else { return }
        do { digest = try await API.shared.digestPreview(); error = nil } catch { self.error = error.localizedDescription }
    }

    private func send() async {
        if isSample { sentNote = "Sent over Telegram."; return }
        sending = true; defer { sending = false }
        do {
            let out = try await API.shared.sendDigest()
            sentNote = out.sent ? "Sent\(out.channel.map { " over \($0)" } ?? "")." : (out.why ?? "It was not sent.")
            if out.sent { sentCount += 1 }
            error = nil
        } catch { self.error = error.localizedDescription }
    }
}
