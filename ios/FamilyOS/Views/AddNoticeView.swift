import SwiftUI
import PhotosUI
import UniformTypeIdentifiers

/// A notice added by hand: pasted text, a photo from the library, or a
/// file. The same gate the share sheet uses, so it is read the same way.
/// Private unless shared with the household; tagged with a child if said.
struct AddNoticeView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) private var dismiss
    @State private var text = ""
    @State private var about: UUID?
    @State private var shared = false
    @State private var photo: PhotosPickerItem?
    @State private var picked: (data: Data, type: String, name: String)?
    @State private var showFiles = false
    @State private var busy = false
    @State private var error: String?
    @State private var said: String?
    @FocusState private var typing: Bool

    private var children: [Member] { session.members.filter(\.isChild) }
    private var canSend: Bool { picked != nil || !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Paste a circular, a message, a link…", text: $text, axis: .vertical).lineLimit(4...10).focused($typing)
                } header: { Text("Text") } footer: { Text("A forwarded WhatsApp message, a mail, a link to a page. The reader finds the dates and what they ask of you.") }
                Section("Or a picture or file") {
                    PhotosPicker(selection: $photo, matching: .images) { Label("Choose a photo", systemImage: "photo") }
                    Button { showFiles = true } label: { Label("Choose a file", systemImage: "doc") }
                    if let picked {
                        HStack {
                            Label(picked.name, systemImage: picked.type.hasPrefix("image/") ? "photo" : "doc").lineLimit(1)
                            Spacer()
                            Button("Remove") { self.picked = nil }.foregroundStyle(Theme.danger)
                        }
                    }
                }
                Section {
                    Picker("About", selection: $about) {
                        Text("Nobody in particular").tag(UUID?.none)
                        ForEach(children) { c in Text(c.displayName).tag(UUID?.some(c.id)) }
                    }
                    Toggle("Share with the household", isOn: $shared)
                } footer: { Text(shared ? "Everyone in the household sees it." : "Only you see it, unless a rule shares it.") }
                if let error { Section { Text(error).foregroundStyle(Theme.danger) } }
                if let said { Section { Label(said, systemImage: "checkmark.circle").foregroundStyle(Theme.success) } }
            }
            .scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
            .navigationTitle("Add a notice")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button(busy ? "Sending…" : "Send") { Task { await send() } }.disabled(!canSend || busy).fontWeight(.semibold) }
            }
            .onChange(of: photo) { _, item in if let item { Task { await take(item) } } }
            .fileImporter(isPresented: $showFiles, allowedContentTypes: [.pdf, .image, .plainText, .data]) { result in
                if case .success(let url) = result { take(url) }
            }
            .onAppear { typing = picked == nil }
        }
    }

    private func take(_ item: PhotosPickerItem) async {
        defer { photo = nil }
        guard let data = try? await item.loadTransferable(type: Data.self) else { error = "That photo could not be read."; return }
        picked = (data, "image/jpeg", "Photo")
    }

    private func take(_ url: URL) {
        let ok = url.startAccessingSecurityScopedResource()
        defer { if ok { url.stopAccessingSecurityScopedResource() } }
        guard let data = try? Data(contentsOf: url) else { error = "That file could not be read."; return }
        let type = UTType(filenameExtension: url.pathExtension)?.preferredMIMEType ?? "application/octet-stream"
        picked = (data, type, url.lastPathComponent)
    }

    private func send() async {
        busy = true; defer { busy = false }
        let tag = children.first { $0.id == about }?.displayName
        let payload: (Data, String) = picked.map { ($0.data, $0.type) } ?? (Data(text.trimmingCharacters(in: .whitespacesAndNewlines).utf8), "text/plain")
        let note = picked != nil && !text.trimmingCharacters(in: .whitespaces).isEmpty ? text : nil
        let kept = await session.doOrKeep(label: "The notice", keep: { Outbox.keepShare(data: payload.0, contentType: payload.1, tag: tag, note: note, shared: shared, label: "a notice added by hand") }) {
            let r = try await API.shared.share(data: payload.0, contentType: payload.1, tag: tag, note: note, shared: shared, requestId: UUID().uuidString)
            said = r.duplicate ? "Already there." : (r.message.isEmpty ? "Received. It is being read." : r.message)
        }
        if let kept { said = kept }
        error = nil
        try? await Task.sleep(for: .seconds(1))
        dismiss()
    }
}

#Preview("Add a notice") { AddNoticeView().environmentObject(PreviewData.session()) }
