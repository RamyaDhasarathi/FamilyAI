// The share sheet's FamilyOS entry: a photo, a PDF, a page or a text from
// any app, posted to the server exactly as the share shortcut posts it.
// Tag a child, choose private or shared, see the server's one-line answer.
import SwiftUI
import UIKit
import UniformTypeIdentifiers

final class ShareViewController: UIViewController {
    override func viewDidLoad() {
        super.viewDidLoad()
        let items = (extensionContext?.inputItems as? [NSExtensionItem]) ?? []
        let root = ShareView(items: items) { [weak self] in
            self?.extensionContext?.completeRequest(returningItems: nil)
        }
        let host = UIHostingController(rootView: root)
        addChild(host)
        host.view.frame = view.bounds
        host.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        view.addSubview(host.view)
        host.didMove(toParent: self)
    }
}

struct Shared {
    let data: Data
    let contentType: String
    let label: String
}

struct ShareView: View {
    let items: [NSExtensionItem]
    let done: () -> Void

    @State private var shared: Shared?
    @State private var tag: String = ""
    @State private var note = ""
    @State private var visible = false
    @State private var busy = false
    @State private var result: String?
    @State private var error: String?

    private var children: [Member] { Server.members.filter(\.isChild) }

    var body: some View {
        NavigationStack {
            Form {
                if !Server.isSignedIn {
                    Text("Open FamilyOS and sign in first.").foregroundStyle(.secondary)
                } else if let result {
                    Text(result)
                } else {
                    Section { Text(shared?.label ?? "Reading what was shared…").foregroundStyle(shared == nil ? .secondary : .primary) }
                    if !children.isEmpty {
                        Section("About") {
                            Picker("Child", selection: $tag) {
                                Text("Nobody in particular").tag("")
                                ForEach(children) { c in Text(c.displayName).tag(c.displayName) }
                            }
                        }
                    }
                    Section {
                        Toggle("Share with the household", isOn: $visible)
                        TextField("A note, optional", text: $note)
                    }
                    if let error { Section { Text(error).foregroundStyle(.red) } }
                }
            }
            .navigationTitle("Send to FamilyOS").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(result == nil ? "Cancel" : "Done") { done() } }
                if result == nil && Server.isSignedIn {
                    ToolbarItem(placement: .confirmationAction) { Button(busy ? "Sending…" : "Send") { Task { await send() } }.disabled(busy || shared == nil) }
                }
            }
            .task { shared = await Self.load(items) }
        }
    }

    private func send() async {
        guard let shared else { return }
        busy = true; defer { busy = false }
        do {
            let r = try await API.shared.share(data: shared.data, contentType: shared.contentType, tag: tag.isEmpty ? nil : tag,
                                               note: note, shared: visible, requestId: UUID().uuidString)
            result = r.message.isEmpty ? (r.duplicate ? "Already there." : "Received.") : r.message
        } catch {
            if Outbox.isTransient(error) {
                Outbox.keepShare(data: shared.data, contentType: shared.contentType, tag: tag.isEmpty ? nil : tag, note: note, shared: visible, label: shared.label)
                result = "No signal right now. Kept on the phone; it goes the next time FamilyOS opens with a connection."
            } else { self.error = error.localizedDescription }
        }
    }

    /// The first thing the sheet carries, as bytes and a content type the
    /// share route understands: an image or a file as itself, a page or a
    /// URL as text/uri-list, a text as text/plain.
    static func load(_ items: [NSExtensionItem]) async -> Shared? {
        let providers = items.flatMap { $0.attachments ?? [] }
        for p in providers where p.hasItemConformingToTypeIdentifier(UTType.image.identifier) {
            if let (data, type) = await bytes(p, UTType.image) { return Shared(data: data, contentType: type.preferredMIMEType ?? "image/jpeg", label: "A picture") }
        }
        for p in providers where p.hasItemConformingToTypeIdentifier(UTType.pdf.identifier) {
            if let (data, _) = await bytes(p, UTType.pdf) { return Shared(data: data, contentType: "application/pdf", label: "A PDF") }
        }
        for p in providers where p.hasItemConformingToTypeIdentifier(UTType.url.identifier) {
            if let url = await item(p, UTType.url) as? URL, !url.isFileURL {
                return Shared(data: Data(url.absoluteString.utf8), contentType: "text/plain", label: url.host ?? url.absoluteString)
            }
        }
        for p in providers where p.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) {
            if let text = await item(p, UTType.plainText) as? String {
                return Shared(data: Data(text.utf8), contentType: "text/plain", label: String(text.prefix(120)))
            }
        }
        for p in providers where p.hasItemConformingToTypeIdentifier(UTType.data.identifier) {
            if let (data, type) = await bytes(p, UTType.data) { return Shared(data: data, contentType: type.preferredMIMEType ?? "application/octet-stream", label: "A file") }
        }
        return nil
    }

    private static func item(_ p: NSItemProvider, _ type: UTType) async -> Any? {
        await withCheckedContinuation { cont in
            p.loadItem(forTypeIdentifier: type.identifier) { item, _ in cont.resume(returning: item) }
        }
    }

    /// NSItemProvider is not marked Sendable, but it is safe to call from
    /// its own completion block, which is what the fallback below does.
    private struct Box: @unchecked Sendable { let p: NSItemProvider }

    private static func bytes(_ p: NSItemProvider, _ type: UTType) async -> (Data, UTType)? {
        let found = p.registeredTypeIdentifiers.compactMap(UTType.init).first { $0.conforms(to: type) } ?? type
        let box = Box(p: p)
        return await withCheckedContinuation { cont in
            box.p.loadDataRepresentation(forTypeIdentifier: found.identifier) { data, _ in
                if let data { cont.resume(returning: (data, found)); return }
                // Some apps hand over a file URL rather than bytes.
                box.p.loadItem(forTypeIdentifier: found.identifier) { item, _ in
                    if let url = item as? URL, let d = try? Data(contentsOf: url) { cont.resume(returning: (d, UTType(filenameExtension: url.pathExtension) ?? found)) }
                    else if let d = item as? Data { cont.resume(returning: (d, found)) }
                    else { cont.resume(returning: nil) }
                }
            }
        }
    }
}
