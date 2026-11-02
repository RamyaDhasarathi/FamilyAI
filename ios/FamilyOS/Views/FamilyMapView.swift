import SwiftUI

/// The family map: how what the household holds connects. One thing in the
/// middle, what touches it on the first ring, what touches those on the
/// second; tap anything to put it in the middle. Below the picture, every
/// connection as a sentence with the notice it came from. The same picture
/// as the console's map (app.js, mapView), built by the server per request.
struct FamilyMapView: View {
    @EnvironmentObject private var session: Session
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var centre: String?
    @State private var touches: GraphTouches?
    @State private var insights: [GraphInsight]?
    @State private var error: String?
    @State private var trail: [String] = []
    @State private var query = ""
    @State private var hits: [GraphNode] = []
    @State private var searched = false
    private let isSample: Bool

    /// `ref` is `type:id` (for example `person:<member id>`); without one the map starts at you.
    init(ref: String? = nil) {
        _centre = State(initialValue: ref)
        isSample = false
    }

    /// A map drawn from data in hand, for previews: nothing is fetched.
    init(sample: GraphTouches, insights: [GraphInsight] = []) {
        _centre = State(initialValue: sample.entity.ref)
        _touches = State(initialValue: sample)
        _insights = State(initialValue: insights)
        isSample = true
    }

    private var home: String? { session.member.map { "person:\($0.id.uuidString.lowercased())" } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.l) {
                VStack(alignment: .leading, spacing: Spacing.xs) {
                    Text("Family map").font(Theme.font(28, .bold)).foregroundStyle(Theme.ink)
                    Text("How what your home holds connects. Tap anything to centre on it.").font(Theme.font(14)).foregroundStyle(Theme.ink3)
                }
                .accessibilityElement(children: .combine).accessibilityAddTraits(.isHeader)
                searchField
                if !hits.isEmpty || (searched && query.trimmingCharacters(in: .whitespaces).count >= 2) { hitList }
                if let error, touches == nil { ErrorState(text: error) { Task { await load() } } }
                if let t = touches {
                    Card(padding: Spacing.s) {
                        VStack(alignment: .leading, spacing: Spacing.m) {
                            MapPicture(touches: t, reduceMotion: reduceMotion) { recentre($0) }
                            legend
                        }
                    }
                    entityCard(t)
                    if let insights, !insights.isEmpty { worthALook(insights) }
                    connections(t)
                } else if error == nil {
                    LoadingRows(count: 3)
                }
                if let error, touches != nil { Text(error).font(Theme.font(13)).foregroundStyle(Theme.warning) }
                BarSpace()
            }
            .padding(Spacing.gutter)
        }
        .paper()
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                if !trail.isEmpty {
                    Button { back() } label: { Image(systemName: "arrow.uturn.backward") }.accessibilityLabel("Back to the last centre")
                }
                if let home, centre != home {
                    Button { recentre(home) } label: { Image(systemName: "person.crop.circle") }.accessibilityLabel("Centre on you")
                }
            }
        }
        .refreshable { await load() }
        .task(id: centre ?? "") { await load() }
        .task(id: query) { await find() }
    }

    // MARK: loading

    private func load() async {
        guard !isSample else { return }
        guard let ref = centre ?? home else { error = "Sign in to see the map."; return }
        if centre == nil { centre = ref; return }   // the task runs again with you in the middle
        do {
            let t = try await API.shared.graphTouches(ref: ref, depth: 2)
            withAnimation(Motion.gentle(reduceMotion)) { touches = t }
            error = nil
        } catch {
            // Something gone, or not visible to this person: back to you, as the console does.
            if let home, ref != home { centre = home; return }
            self.error = error.localizedDescription
        }
        if insights == nil { insights = (try? await API.shared.graphInsights()) ?? [] }
    }

    private func find() async {
        let q = query.trimmingCharacters(in: .whitespaces)
        guard q.count >= 2, !isSample else { hits = []; searched = false; return }
        try? await Task.sleep(for: .milliseconds(250))
        guard !Task.isCancelled else { return }
        hits = (try? await API.shared.graphFind(q)) ?? []
        searched = true
    }

    private func recentre(_ ref: String) {
        query = ""; hits = []
        guard ref != centre else { return }
        if let centre { trail.append(centre) }
        centre = ref
    }

    private func back() {
        guard let last = trail.popLast() else { return }
        centre = last
    }

    // MARK: pieces

    private var searchField: some View {
        HStack(spacing: Spacing.s) {
            Image(systemName: "magnifyingglass").foregroundStyle(Theme.ink3).accessibilityHidden(true)
            TextField("Find a person, shop, clinic or document", text: $query)
                .font(Theme.font(15)).foregroundStyle(Theme.ink)
                .autocorrectionDisabled().textInputAutocapitalization(.never).submitLabel(.search)
                .accessibilityLabel("Find on the map")
            if !query.isEmpty {
                Button { query = "" } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(Theme.ink3) }
                    .buttonStyle(.plain).accessibilityLabel("Clear")
            }
        }
        .padding(.horizontal, Spacing.m).frame(minHeight: 44)
        .background(Theme.card).clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(Theme.line, lineWidth: 0.5))
    }

    private var hitList: some View {
        ListCard {
            if hits.isEmpty { Text("Nothing by that name.").font(Theme.font(14)).foregroundStyle(Theme.ink3).padding(Spacing.m).frame(maxWidth: .infinity, alignment: .leading) }
            ForEach(Array(hits.enumerated()), id: \.element.ref) { i, n in
                if i > 0 { RowDivider(inset: 40) }
                Button { recentre(n.ref) } label: {
                    HStack(spacing: Spacing.m) {
                        MapDot(kind: MapKind.of(n.type), size: 24)
                        Text(n.label).font(Theme.font(15)).foregroundStyle(Theme.ink).lineLimit(2)
                        Spacer(minLength: 0)
                        Text(MapKind.of(n.type).singular).font(Theme.font(12)).foregroundStyle(Theme.ink3)
                    }
                    .padding(.horizontal, Spacing.s).frame(minHeight: 44).contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityHint("Centres the map here")
            }
        }
    }

    private var legend: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 120), alignment: .leading)], alignment: .leading, spacing: Spacing.xs) {
            ForEach(MapKind.allCases, id: \.self) { k in
                HStack(spacing: 6) {
                    Circle().fill(k.color).frame(width: 9, height: 9)
                    Text(k.plural).font(Theme.font(12)).foregroundStyle(Theme.ink3)
                }
            }
        }
        .padding(.horizontal, Spacing.xs)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Key: " + MapKind.allCases.map(\.plural).joined(separator: ", "))
    }

    private func entityCard(_ t: GraphTouches) -> some View {
        let e = t.entity, kind = MapKind.of(e.type)
        let facts = [e.due.flatMap(day).map { "due " + $0 }, e.expiresOn.flatMap(day).map { "expires " + $0 },
                     e.warrantyUntil.flatMap(day).map { "warranty to " + $0 }, e.kind.map { $0.replacingOccurrences(of: "_", with: " ") }].compactMap { $0 }
        return Card {
            HStack(spacing: Spacing.m) {
                Glyph(symbol: kind.symbol, tint: kind.color, size: 40)
                VStack(alignment: .leading, spacing: 2) {
                    Text(e.label).font(Theme.font(17, .semibold)).foregroundStyle(Theme.ink)
                    Text(([kind.singular] + facts).joined(separator: " · ")).font(Theme.font(13)).foregroundStyle(Theme.ink3)
                    Text(t.count == 0 ? "Nothing is connected to this yet." : "\(t.count) connected within two steps").font(Theme.font(12)).foregroundStyle(Theme.ink3)
                }
                Spacer(minLength: 0)
            }
            .accessibilityElement(children: .combine)
        }
    }

    private func worthALook(_ list: [GraphInsight]) -> some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            SectionLabel(title: "Worth a look")
            ListCard {
                ForEach(Array(list.enumerated()), id: \.element.key) { i, n in
                    if i > 0 { RowDivider(inset: Spacing.m) }
                    HStack(alignment: .top, spacing: Spacing.m) {
                        RoundedRectangle(cornerRadius: 1.5).fill(Theme.primary).frame(width: 3).accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(n.title).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                            Text(n.why).font(Theme.font(12)).foregroundStyle(Theme.ink3)
                        }
                        Spacer(minLength: 0)
                        Button("Open") { recentre(n.ref) }.font(Theme.font(14, .semibold)).foregroundStyle(Theme.primary)
                            .frame(minWidth: 44, minHeight: 44).accessibilityLabel("Open \(n.title) on the map")
                    }
                    .padding(.horizontal, Spacing.s).padding(.vertical, Spacing.xs)
                }
            }
        }
    }

    @ViewBuilder private func connections(_ t: GraphTouches) -> some View {
        let drawn = MapLayout(t.connections, centre: t.entity.ref, side: 1).drawn.count
        ForEach(MapKind.allCases, id: \.self) { kind in
            let items = t.connections.filter { MapKind.of($0.node.type) == kind }
            if !items.isEmpty {
                VStack(alignment: .leading, spacing: Spacing.s) {
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text(kind.plural).font(Theme.font(17, .semibold)).foregroundStyle(Theme.ink)
                        Text("\(items.count)").font(Theme.font(14)).foregroundStyle(Theme.ink3)
                    }
                    .accessibilityElement(children: .combine).accessibilityAddTraits(.isHeader)
                    ListCard {
                        ForEach(Array(items.enumerated()), id: \.element.id) { i, c in
                            if i > 0 { RowDivider(inset: Spacing.m) }
                            connectionRow(c, kind: kind)
                        }
                    }
                }
            }
        }
        if t.connections.count > drawn {
            Text("\(t.connections.count - drawn) more not drawn; they are listed above.").font(Theme.font(12)).foregroundStyle(Theme.ink3)
        }
    }

    private func connectionRow(_ c: GraphConnection, kind: MapKind) -> some View {
        VStack(alignment: .leading, spacing: Spacing.s) {
            HStack(alignment: .firstTextBaseline, spacing: Spacing.s) {
                Circle().fill(kind.color).frame(width: 8, height: 8).accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text(c.node.label).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink)
                    if let phrase = c.last?.phrase { Text(phrase).font(Theme.font(12)).foregroundStyle(Theme.ink3) }
                    if let quote = c.last?.quote, !quote.isEmpty { Text("“\(quote)”").font(Theme.font(12)).foregroundStyle(Theme.ink2).lineLimit(3) }
                }
            }
            .accessibilityElement(children: .combine)
            HStack(spacing: Spacing.s) {
                if let id = c.last?.sourceArtifactId {
                    NavigationLink { NoticeView(artifactId: id, title: c.node.label) } label: { pill("Read the notice") }
                        .buttonStyle(.plain)
                }
                Button { recentre(c.node.ref) } label: { pill("Centre here") }
                    .buttonStyle(.plain).accessibilityLabel("Centre the map on \(c.node.label)")
            }
            .padding(.leading, 16)
        }
        .padding(.horizontal, Spacing.s).padding(.vertical, Spacing.s)
    }

    private func pill(_ title: String) -> some View {
        Text(title).font(Theme.font(13, .medium)).foregroundStyle(Theme.ink)
            .padding(.horizontal, 12).frame(minHeight: 36)
            .background(Theme.card).overlay(Capsule().stroke(Theme.line, lineWidth: 1)).clipShape(Capsule())
            .contentShape(Capsule())
    }

    private func day(_ s: String) -> String? { API.parseDate(s).map { Format.dayYear.string(from: $0) } }
}

// MARK: the picture

/// The kinds of thing on the map, in the order the list groups them: the console's colours, and a mark each so colour is never the only sign.
enum MapKind: String, CaseIterable {
    case person, obligation, document, warranty, medication, org, artifact

    static func of(_ type: String) -> MapKind { MapKind(rawValue: type) ?? .artifact }

    var plural: String {
        switch self {
        case .person: return "People"; case .obligation: return "Dates and tasks"; case .document: return "Documents"
        case .warranty: return "Warranties"; case .medication: return "Medicines"; case .org: return "Shops and clinics"; case .artifact: return "Notices"
        }
    }
    var singular: String {
        switch self {
        case .person: return "Person"; case .obligation: return "Date or task"; case .document: return "Document"
        case .warranty: return "Warranty"; case .medication: return "Medicine"; case .org: return "Shop or clinic"; case .artifact: return "Notice"
        }
    }
    var color: Color {
        switch self {
        case .person: return Theme.primary
        case .obligation: return Color(red: 0.886, green: 0.604, blue: 0.122)
        case .document: return Theme.green
        case .warranty: return Color(red: 0.545, green: 0.435, blue: 0.839)
        case .medication: return Theme.red
        case .org: return Color(red: 0.361, green: 0.561, blue: 0.608)
        case .artifact: return Theme.ink3
        }
    }
    var symbol: String {
        switch self {
        case .person: return "person.fill"; case .obligation: return "calendar"; case .document: return "doc.text.fill"
        case .warranty: return "checkmark.shield.fill"; case .medication: return "pills.fill"; case .org: return "building.2.fill"; case .artifact: return "envelope.fill"
        }
    }
}

/// Where each node sits: the first ring evenly round the centre, the second
/// fanned out behind the node it is reached through. The console's mapPos,
/// on a square of side `side`. A second-ring node whose way in is not drawn is left to the list.
struct MapLayout {
    struct Spot { let point: CGPoint; let angle: Double; let parent: CGPoint? }
    let ring1: [GraphConnection]
    let ring2: [GraphConnection]
    let at: [String: Spot]
    var drawn: [GraphConnection] { ring1 + ring2 }

    init(_ conns: [GraphConnection], centre ref: String, side: CGFloat) {
        let c = CGPoint(x: side / 2, y: side / 2), r1 = side * 0.29, r2 = side * 0.44
        let first = Array(conns.filter { $0.distance == 1 }.prefix(12))
        var at: [String: Spot] = [:]
        for (i, conn) in first.enumerated() {
            let a = -Double.pi / 2 + Double(i) * 2 * .pi / Double(max(first.count, 1))
            at[conn.node.ref] = Spot(point: CGPoint(x: c.x + r1 * cos(a), y: c.y + r1 * sin(a)), angle: a, parent: nil)
        }
        var byParent: [String: [GraphConnection]] = [:]
        var order: [String] = []
        for conn in conns where conn.distance == 2 {
            guard let step = conn.path.first else { continue }
            let parent = step.from == ref ? step.to : step.from
            guard at[parent] != nil else { continue }
            if byParent[parent] == nil { order.append(parent) }
            byParent[parent, default: []].append(conn)
        }
        var second: [GraphConnection] = []
        for parent in order {
            guard let base = at[parent], second.count < 18 else { continue }
            let list = Array(byParent[parent]!.prefix(18 - second.count))
            let step = min(0.3, 1.1 / Double(max(list.count, 1)))
            for (i, conn) in list.enumerated() {
                let a = base.angle + (Double(i) - Double(list.count - 1) / 2) * step
                at[conn.node.ref] = Spot(point: CGPoint(x: c.x + r2 * cos(a), y: c.y + r2 * sin(a)), angle: a, parent: base.point)
            }
            second += list
        }
        ring1 = first; ring2 = second; self.at = at
    }
}

/// A coloured disc with the kind's mark in it.
struct MapDot: View {
    let kind: MapKind
    var size: CGFloat
    var body: some View {
        Circle().fill(kind.color).frame(width: size, height: size)
            .overlay(Image(systemName: kind.symbol).font(.system(size: size * 0.46, weight: .semibold)).foregroundStyle(.white))
            .accessibilityHidden(true)
    }
}

/// The drawing: lines first, then the second ring (unlabelled, it is too
/// close together to read), the first ring with short names, the centre.
struct MapPicture: View {
    let touches: GraphTouches
    let reduceMotion: Bool
    let tap: (String) -> Void

    var body: some View {
        GeometryReader { geo in
            let side = geo.size.width
            let layout = MapLayout(touches.connections, centre: touches.entity.ref, side: side)
            let c = CGPoint(x: side / 2, y: side / 2)
            ZStack {
                Path { p in
                    for conn in layout.ring1 { if let s = layout.at[conn.node.ref] { p.move(to: c); p.addLine(to: s.point) } }
                }.stroke(Theme.ink3.opacity(0.45), lineWidth: 1.2)
                Path { p in
                    for conn in layout.ring2 { if let s = layout.at[conn.node.ref] { p.move(to: s.parent ?? c); p.addLine(to: s.point) } }
                }.stroke(Theme.ink3.opacity(0.3), style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
                ForEach(layout.ring2) { conn in
                    if let s = layout.at[conn.node.ref] { node(conn.node, size: 20, label: false).position(s.point) }
                }
                ForEach(layout.ring1) { conn in
                    if let s = layout.at[conn.node.ref] { node(conn.node, size: 30, label: true).position(s.point) }
                }
                MapDot(kind: MapKind.of(touches.entity.type), size: 52)
                    .overlay { label(touches.entity.label, max: 24, bold: true).offset(y: 26 + 11) }
                    .position(c)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("In the middle: \(touches.entity.label), \(MapKind.of(touches.entity.type).singular)")
            }
            .animation(Motion.gentle(reduceMotion), value: touches.entity.ref)
        }
        .aspectRatio(1, contentMode: .fit)
        .dynamicTypeSize(...DynamicTypeSize.xLarge)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Connections around \(touches.entity.label)")
    }

    private func node(_ n: GraphNode, size: CGFloat, label show: Bool) -> some View {
        Button { tap(n.ref) } label: {
            MapDot(kind: MapKind.of(n.type), size: size)
                .frame(width: 44, height: 44).contentShape(Circle())
                .overlay { if show { label(n.label, max: 14, bold: false).offset(y: size / 2 + 10) } }
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(n.label), \(MapKind.of(n.type).singular)")
        .accessibilityHint("Centres the map here")
    }

    private func label(_ text: String, max: Int, bold: Bool) -> some View {
        Text(text.count > max ? String(text.prefix(max - 1)) + "…" : text)
            .font(Theme.font(11, bold ? .semibold : .medium)).foregroundStyle(bold ? Theme.ink : Theme.ink2)
            .lineLimit(1).fixedSize()
            .allowsHitTesting(false).accessibilityHidden(true)
    }
}

// MARK: previews

extension PreviewData {
    static let graphTouches: GraphTouches = decode("""
    {"entity":{"ref":"person:\(amma)","type":"person","label":"Kanimozhi","role":"guardian"},"count":8,"connections":[
      {"node":{"ref":"obligation:bbbbbbbb-0000-0000-0000-000000000011","type":"obligation","label":"PTM for Grade 4","due":"\(day(2))","status":"accepted"},"distance":1,
       "path":[{"from":"obligation:bbbbbbbb-0000-0000-0000-000000000011","relation":"about","to":"person:\(amma)","source_artifact_id":"aaaaaaaa-0000-0000-0000-000000000001","quote":"Parents are requested to attend the PTM","phrase":"PTM for Grade 4 is about Kanimozhi"}]},
      {"node":{"ref":"document:eeeeeeee-0000-0000-0000-000000000001","type":"document","label":"Passport","kind":"passport","expires_on":"2029-03-12"},"distance":1,
       "path":[{"from":"document:eeeeeeee-0000-0000-0000-000000000001","relation":"held_by","to":"person:\(amma)","source_artifact_id":"aaaaaaaa-0000-0000-0000-000000000006","quote":null,"phrase":"Passport is held by Kanimozhi"}]},
      {"node":{"ref":"medication:ffffffff-0000-0000-0000-000000000001","type":"medication","label":"Amoxicillin 500 mg"},"distance":1,
       "path":[{"from":"medication:ffffffff-0000-0000-0000-000000000001","relation":"for","to":"person:\(amma)","source_artifact_id":"aaaaaaaa-0000-0000-0000-000000000008","quote":null,"phrase":"Amoxicillin 500 mg is for Kanimozhi"}]},
      {"node":{"ref":"artifact:aaaaaaaa-0000-0000-0000-000000000009","type":"artifact","label":"Croma invoice: Samsung refrigerator"},"distance":1,
       "path":[{"from":"artifact:aaaaaaaa-0000-0000-0000-000000000009","relation":"about","to":"person:\(amma)","source_artifact_id":"aaaaaaaa-0000-0000-0000-000000000009","quote":null,"phrase":"Croma invoice: Samsung refrigerator is about Kanimozhi"}]},
      {"node":{"ref":"artifact:aaaaaaaa-0000-0000-0000-000000000001","type":"artifact","label":"Term 2 circular"},"distance":2,
       "path":[{"from":"obligation:bbbbbbbb-0000-0000-0000-000000000011","relation":"about","to":"person:\(amma)","source_artifact_id":"aaaaaaaa-0000-0000-0000-000000000001","quote":null,"phrase":"PTM for Grade 4 is about Kanimozhi"},
               {"from":"obligation:bbbbbbbb-0000-0000-0000-000000000011","relation":"from","to":"artifact:aaaaaaaa-0000-0000-0000-000000000001","source_artifact_id":"aaaaaaaa-0000-0000-0000-000000000001","quote":null,"phrase":"PTM for Grade 4 comes from Term 2 circular"}]},
      {"node":{"ref":"org:passport-seva","type":"org","label":"Passport Seva"},"distance":2,
       "path":[{"from":"document:eeeeeeee-0000-0000-0000-000000000001","relation":"held_by","to":"person:\(amma)","source_artifact_id":"aaaaaaaa-0000-0000-0000-000000000006","quote":null,"phrase":"Passport is held by Kanimozhi"},
               {"from":"document:eeeeeeee-0000-0000-0000-000000000001","relation":"issued_by","to":"org:passport-seva","source_artifact_id":"aaaaaaaa-0000-0000-0000-000000000006","quote":null,"phrase":"Passport was issued by Passport Seva"}]},
      {"node":{"ref":"org:apollo-clinic","type":"org","label":"Apollo Clinic"},"distance":2,
       "path":[{"from":"medication:ffffffff-0000-0000-0000-000000000001","relation":"for","to":"person:\(amma)","source_artifact_id":"aaaaaaaa-0000-0000-0000-000000000008","quote":null,"phrase":"Amoxicillin 500 mg is for Kanimozhi"},
               {"from":"medication:ffffffff-0000-0000-0000-000000000001","relation":"prescribed_at","to":"org:apollo-clinic","source_artifact_id":"aaaaaaaa-0000-0000-0000-000000000008","quote":null,"phrase":"Amoxicillin 500 mg was prescribed at Apollo Clinic"}]},
      {"node":{"ref":"warranty:99999999-0000-0000-0000-000000000001","type":"warranty","label":"Samsung refrigerator","warranty_until":"\(day(20))"},"distance":2,
       "path":[{"from":"artifact:aaaaaaaa-0000-0000-0000-000000000009","relation":"about","to":"person:\(amma)","source_artifact_id":"aaaaaaaa-0000-0000-0000-000000000009","quote":null,"phrase":"Croma invoice: Samsung refrigerator is about Kanimozhi"},
               {"from":"warranty:99999999-0000-0000-0000-000000000001","relation":"from","to":"artifact:aaaaaaaa-0000-0000-0000-000000000009","source_artifact_id":"aaaaaaaa-0000-0000-0000-000000000009","quote":null,"phrase":"Samsung refrigerator comes from Croma invoice: Samsung refrigerator"}]}
    ]}
    """)

    static let graphInsights: [GraphInsight] = decode("""
    [
      {"kind":"busy_person","key":"busy:person:\(noah):41","ref":"person:\(noah)","title":"Noah has 4 things in the next 7 days","why":"PTM (Thu 16 Oct); Science fair (Fri 17 Oct); Swimming (Sat 18 Oct); Library books (Mon 20 Oct)"},
      {"kind":"warranty_ending","key":"warranty_ending:warranty:99999999-0000-0000-0000-000000000001","ref":"warranty:99999999-0000-0000-0000-000000000001","title":"The warranty on Samsung refrigerator ends 3 Nov","why":"If anything is wrong with it, now is the time to claim; after that it is on you."}
    ]
    """)
}

#Preview("Family map") {
    NavigationStack { FamilyMapView(sample: PreviewData.graphTouches, insights: PreviewData.graphInsights) }.environmentObject(PreviewData.session())
}

#Preview("Family map · dark, large text") {
    NavigationStack { FamilyMapView(sample: PreviewData.graphTouches, insights: PreviewData.graphInsights) }
        .environmentObject(PreviewData.session()).preferredColorScheme(.dark).dynamicTypeSize(.xxxLarge)
}
