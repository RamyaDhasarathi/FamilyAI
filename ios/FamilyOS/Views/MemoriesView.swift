import SwiftUI

/// Memories: the photographs the family shared from their phones. The
/// latest as a highlight, the rest as a grid. Pictures sorted as documents
/// are notices and stay out.
struct MemoriesView: View {
    @EnvironmentObject var session: Session
    @State private var pics: [Artifact] = []
    @State private var chip = "Highlights"
    @State private var error: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    ScreenHeader(title: "Memories", subtitle: pics.isEmpty ? nil : "\(pics.count) photos the family shared") { HeaderButton(symbol: "magnifyingglass", label: "Search", value: "search") }
                    HStack(spacing: 8) {
                        ForEach(["Highlights", "Photos"], id: \.self) { c in Button { withAnimation(.snappy) { chip = c } } label: { Chip(text: c, on: chip == c) }.buttonStyle(.plain) }
                        Spacer()
                    }
                    ErrorLine(text: error)
                    if pics.isEmpty && error == nil {
                        EmptyState(symbol: "photo.on.rectangle", title: "Nothing here yet", text: "Share a photo from your phone with FamilyOS and it appears here.")
                    } else if chip == "Highlights" {
                        if let first = pics.first {
                            NavigationLink(value: first.id) { HighlightCard(a: first, who: session.name(of: first.submittedBy)) }.buttonStyle(.plain)
                        }
                        LazyVGrid(columns: [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)], spacing: 8) {
                            ForEach(pics.dropFirst().prefix(12)) { a in NavigationLink(value: a.id) { PhotoTile(a: a, caption: true) }.buttonStyle(.plain) }
                        }
                    } else {
                        LazyVGrid(columns: [GridItem(.flexible(), spacing: 3), GridItem(.flexible(), spacing: 3), GridItem(.flexible(), spacing: 3)], spacing: 3) {
                            ForEach(pics) { a in NavigationLink(value: a.id) { Thumb(id: a.id).aspectRatio(1, contentMode: .fill).clipShape(RoundedRectangle(cornerRadius: 6)) }.buttonStyle(.plain).accessibilityLabel("Photo, " + Format.dayYear.string(from: a.receivedAt)) }
                        }
                    }
                    BarSpace()
                }
                .padding(.horizontal, 16)
            }
            .paper()
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(for: UUID.self) { id in NoticeView(artifactId: id, title: "A photo") }
            .navigationDestination(for: String.self) { key in if key == "settings" { SettingsView() } else { SearchView() } }
            .task { await load() }
            .refreshable { await load() }
        }
    }

    private func load() async {
        do {
            let all = try await API.shared.artifacts(limit: 200)
            pics = all.filter { a in a.isMemory }.sorted { $0.receivedAt > $1.receivedAt }
            error = nil
        } catch { self.error = error.localizedDescription }
    }
}

struct HighlightCard: View {
    let a: Artifact
    let who: String?
    var body: some View {
        ZStack(alignment: .bottomLeading) {
            Thumb(id: a.id).frame(height: 230)
            LinearGradient(colors: [.clear, .black.opacity(0.55)], startPoint: .center, endPoint: .bottom)
            VStack(alignment: .leading, spacing: 3) {
                Text(a.headline ?? a.note ?? "A photo").font(Theme.font(20, .medium, .serif)).foregroundStyle(.white).lineLimit(2)
                Text([who.map { "Shared by \($0)" }, Format.dayYear.string(from: a.receivedAt)].compactMap { $0 }.joined(separator: " · ")).font(Theme.font(12)).foregroundStyle(.white.opacity(0.85))
            }.padding(14)
        }
        .frame(height: 230).clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
    }
}

struct PhotoTile: View {
    let a: Artifact
    var caption: Bool = false
    var body: some View {
        ZStack(alignment: .bottomLeading) {
            Thumb(id: a.id).frame(height: 150)
            if caption {
                LinearGradient(colors: [.clear, .black.opacity(0.5)], startPoint: .center, endPoint: .bottom)
                Text(Format.day.string(from: a.receivedAt)).font(Theme.font(12, .medium)).foregroundStyle(.white).padding(10)
            }
        }
        .frame(height: 150).clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

/// A picture, fetched with the bearer token (AsyncImage cannot send one).
struct Thumb: View {
    let id: UUID
    @State private var image: UIImage?
    var body: some View {
        GeometryReader { geo in
            ZStack {
                Theme.line
                if let image { Image(uiImage: image).resizable().scaledToFill() }
            }
            .frame(width: geo.size.width, height: geo.size.height).clipped()
        }
        .task { if image == nil, let data = try? await API.shared.picture(id) { image = UIImage(data: data) } }
    }
}
