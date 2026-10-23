// The look: the console's palette and type on the phone. Warm paper, ink,
// a coral primary, one hue per space, serif for the greeting.
import SwiftUI

enum Theme {
    static let paper = Color(light: Color(red: 0.973, green: 0.965, blue: 0.945), dark: Color(red: 0.11, green: 0.11, blue: 0.105))
    static let card = Color(light: .white, dark: Color(red: 0.16, green: 0.16, blue: 0.15))
    static let ink = Color(light: Color(red: 0.125, green: 0.125, blue: 0.118), dark: Color(red: 0.95, green: 0.94, blue: 0.92))
    static let ink2 = Color(light: Color(red: 0.29, green: 0.28, blue: 0.26), dark: Color(red: 0.80, green: 0.79, blue: 0.76))
    static let ink3 = Color(light: Color(red: 0.47, green: 0.45, blue: 0.43), dark: Color(red: 0.62, green: 0.61, blue: 0.58))
    static let line = Color.primary.opacity(0.08)
    static let primary = Color(light: Color(red: 0.824, green: 0.373, blue: 0.275), dark: Color(red: 0.94, green: 0.55, blue: 0.43))
    static let primaryTint = primary.opacity(0.10)
    static let amber = Color(red: 0.88, green: 0.66, blue: 0.24)
    static let green = Color(light: Color(red: 0.31, green: 0.54, blue: 0.37), dark: Color(red: 0.61, green: 0.82, blue: 0.64))
    static let red = Color(red: 0.72, green: 0.26, blue: 0.23)
    static let radius: CGFloat = 18
    /// Semantic aliases: what a colour means, so a screen never picks a hue.
    static var success: Color { green }
    static var warning: Color { amber }
    static var danger: Color { red }
    /// A hairline that is a line when the person asked for more contrast.
    static func line(contrast: ColorSchemeContrast) -> Color { contrast == .increased ? Color.primary.opacity(0.35) : line }

    /// A type size from the design, as the nearest text style so it follows
    /// Dynamic Type; weight and design ride along.
    static func font(_ size: CGFloat, _ weight: Font.Weight = .regular, _ design: Font.Design = .default) -> Font {
        let style: Font.TextStyle
        switch size {
        case ..<11.5: style = .caption2
        case ..<12.5: style = .caption
        case ..<13.5: style = .footnote
        case ..<14.5: style = .subheadline
        case ..<15.5: style = .callout
        case ..<17.5: style = .body
        case ..<21: style = .title3
        case ..<26: style = .title2
        case ..<31: style = .title
        default: style = .largeTitle
        }
        return .system(style, design: design).weight(weight)
    }
}

extension Color {
    init(light: Color, dark: Color) {
        self.init(UIColor { $0.userInterfaceStyle == .dark ? UIColor(dark) : UIColor(light) })
    }
}

/// Spacing on an 4-point grid. Screens use these, never bare numbers.
enum Spacing {
    static let xs: CGFloat = 4, s: CGFloat = 8, m: CGFloat = 12, l: CGFloat = 16, xl: CGFloat = 24, xxl: CGFloat = 32
    /// The side gutter of every screen.
    static let gutter: CGFloat = 16
}

/// Motion that steps aside when the person asked it to.
enum Motion {
    static func spring(_ reduce: Bool) -> Animation? { reduce ? nil : .snappy }
    static func gentle(_ reduce: Bool) -> Animation? { reduce ? nil : .smooth(duration: 0.35) }
}

/// A card: white on paper, soft corners, a hairline that firms up under
/// Increase Contrast. Content surfaces are opaque; glass is for controls.
struct Card<Content: View>: View {
    var padding: CGFloat = 14
    @ViewBuilder let content: Content
    @Environment(\.colorSchemeContrast) private var contrast
    var body: some View {
        content
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.card)
            .clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous).stroke(Theme.line(contrast: contrast), lineWidth: contrast == .increased ? 1 : 0.5))
    }
}

/// A section heading with an optional link on the right.
struct Heading: View {
    let title: String
    var link: String? = nil
    var action: (() -> Void)? = nil
    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title).font(Theme.font(17, .semibold)).foregroundStyle(Theme.ink)
            Spacer()
            if let link { Button(link) { action?() }.font(.subheadline).foregroundStyle(Theme.primary) }
        }
        .padding(.horizontal, 2)
    }
}

/// A round tinted glyph, the mark of a space or a kind.
struct Glyph: View {
    let symbol: String
    var tint: Color = Theme.primary
    var size: CGFloat = 36
    var body: some View {
        Image(systemName: symbol).font(.system(size: size * 0.42, weight: .medium)).foregroundStyle(tint)
            .frame(width: size, height: size).background(tint.opacity(0.14))
            .clipShape(RoundedRectangle(cornerRadius: size * 0.3, style: .continuous))
            .accessibilityHidden(true)
    }
}

/// A member's face: the initial in a ring, coloured by role.
struct Avatar: View {
    let member: Member
    var size: CGFloat = 44
    var tint: Color { member.isChild ? Space.school.color : Theme.primary }
    var body: some View {
        Text(String(member.displayName.prefix(1)))
            .font(.system(size: size * 0.42, weight: .semibold, design: .serif)).foregroundStyle(tint)
            .frame(width: size, height: size).background(tint.opacity(0.14)).clipShape(Circle())
            .overlay(Circle().stroke(tint.opacity(0.5), lineWidth: 1.5))
            .accessibilityLabel(member.displayName)
    }
}

struct Chip: View {
    let text: String
    var on: Bool = false
    var tint: Color = Theme.primary
    var body: some View {
        Text(text).font(Theme.font(13, .medium))
            .padding(.horizontal, 12).padding(.vertical, 7)
            .background(on ? tint.opacity(0.14) : Theme.card)
            .foregroundStyle(on ? tint : Theme.ink2)
            .clipShape(Capsule()).overlay(Capsule().stroke(on ? tint.opacity(0.4) : Theme.line, lineWidth: 0.5))
    }
}

struct Tag: View {
    let text: String
    var symbol: String? = nil
    var tint: Color = Theme.ink3
    var body: some View {
        HStack(spacing: 4) {
            if let symbol { Image(systemName: symbol).font(.system(size: 10, weight: .semibold)) }
            Text(text).font(Theme.font(12, .medium))
        }
        .padding(.horizontal, 9).padding(.vertical, 5).foregroundStyle(tint).background(tint.opacity(0.12)).clipShape(Capsule())
    }
}

/// Coral filled button, the one action on a card.
struct PrimaryButton: View {
    let title: String
    let action: () -> Void
    var body: some View {
        if #available(iOS 26, *) {
            Button(action: action) { Text(title).font(Theme.font(15, .semibold)).frame(maxWidth: .infinity).padding(.vertical, 6) }
                .buttonStyle(.glassProminent).tint(Theme.primary)
        } else {
            Button(action: action) {
                Text(title).font(Theme.font(15, .semibold)).foregroundStyle(.white)
                    .frame(maxWidth: .infinity).padding(.vertical, 13)
                    .background(Theme.primary).clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
        }
    }
}

struct GhostButton: View {
    let title: String
    let action: () -> Void
    var body: some View {
        if #available(iOS 26, *) {
            Button(action: action) { Text(title).font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink).frame(maxWidth: .infinity).padding(.vertical, 6) }
                .buttonStyle(.glass)
        } else {
            Button(action: action) {
                Text(title).font(Theme.font(15, .semibold)).foregroundStyle(Theme.ink)
                    .frame(maxWidth: .infinity).padding(.vertical, 13)
                    .background(Theme.card).clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(Theme.line, lineWidth: 1))
            }
        }
    }
}

/// One line of a timeline: the time, a glyph, what, who.
struct TimelineRow: View {
    let time: String?
    let symbol: String
    let tint: Color
    let title: String
    let sub: String?
    var last: Bool = false
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Text(time ?? "").font(Theme.font(12, .medium)).foregroundStyle(Theme.ink3).lineLimit(2).multilineTextAlignment(.trailing).frame(width: 64, alignment: .trailing).padding(.top, 10)
            VStack(spacing: 0) {
                Circle().fill(tint).frame(width: 6, height: 6).padding(.top, 14)
                if !last { Rectangle().fill(Theme.line).frame(width: 1).frame(maxHeight: .infinity) }
            }.frame(width: 6)
            HStack(spacing: 10) {
                Glyph(symbol: symbol, tint: tint, size: 34)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Theme.font(15, .medium)).foregroundStyle(Theme.ink).lineLimit(2)
                    if let sub, !sub.isEmpty { Text(sub).font(Theme.font(12)).foregroundStyle(Theme.ink3).lineLimit(1) }
                }
                Spacer(minLength: 0)
            }
            .padding(10).background(Theme.card).clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(Theme.line, lineWidth: 0.5))
            .padding(.bottom, last ? 0 : 8)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel([time, title, sub].compactMap { $0 }.joined(separator: ", "))
    }
}

extension View {
    /// Every screen: paper behind, no list chrome.
    func paper() -> some View { self.background(Theme.paper.ignoresSafeArea()) }
}

/// What a brief item is about, for its glyph and colour.
func kindOf(_ i: BriefItem) -> (String, Color) {
    switch i.action {
    case "pay": return ("indianrupeesign.circle", Space.money.color)
    case "attend", "arrive": return ("calendar", Space.school.color)
    case "submit", "bring": return ("doc.text", Space.school.color)
    case "renew": return ("arrow.triangle.2.circlepath", Space.health.color)
    default:
        switch i.reason {
        case "unbilled": return ("exclamationmark.circle", Space.money.color)
        case "clash": return ("exclamationmark.triangle", Theme.amber)
        case "school_year": return ("graduationcap", Space.school.color)
        case "birthday": return ("gift", Space.health.color)
        case "majority": return ("person.badge.key", Theme.primary)
        case "money": return ("banknote", Space.money.color)
        case "prepare": return ("checklist", Space.school.color)
        case "handled": return ("checkmark.circle", Theme.green)
        default: return ("bell", Theme.primary)
        }
    }
}

func greeting(for date: Date = Date()) -> String {
    let h = Calendar.current.component(.hour, from: date)
    return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"
}

// MARK: Liquid Glass (iOS 26), with the flat look as the fallback

/// Glass for the navigation layer only: bars, floating controls, the orb.
/// Before iOS 26, and whenever the person has Reduce Transparency on, the
/// same shape is drawn as an opaque card so nothing depends on the material.
struct GlassShape: ViewModifier {
    enum Kind { case capsule, circle, rect(CGFloat) }
    let kind: Kind
    var tint: Color? = nil
    var interactive: Bool = true
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast

    private var shape: AnyShape {
        switch kind {
        case .capsule: return AnyShape(Capsule())
        case .circle: return AnyShape(Circle())
        case .rect(let r): return AnyShape(RoundedRectangle(cornerRadius: r, style: .continuous))
        }
    }

    func body(content: Content) -> some View {
        if #available(iOS 26, *), !reduceTransparency {
            if let tint { content.glassEffect(.regular.tint(tint).interactive(interactive), in: shape) }
            else { content.glassEffect(.regular.interactive(interactive), in: shape) }
        } else {
            content.background(tint ?? Theme.card).clipShape(shape)
                .overlay(shape.stroke(tint == nil ? Theme.line(contrast: contrast) : .clear, lineWidth: 0.5))
                .shadow(color: .black.opacity(tint == nil ? 0.06 : 0), radius: 8, y: 2)
        }
    }
}

extension View {
    /// A floating control on the navigation layer. `tint` only for the one primary action.
    func glassCapsule(tint: Color? = nil, interactive: Bool = true) -> some View { modifier(GlassShape(kind: .capsule, tint: tint, interactive: interactive)) }
    func glassCircle(tint: Color? = nil) -> some View { modifier(GlassShape(kind: .circle, tint: tint)) }
    func glassRect(_ radius: CGFloat = Theme.radius) -> some View { modifier(GlassShape(kind: .rect(radius), interactive: false)) }

    /// The system's glass button styles when they exist.
    @ViewBuilder
    func glassButton(prominent: Bool) -> some View {
        if #available(iOS 26, *) {
            if prominent { self.buttonStyle(.glassProminent) } else { self.buttonStyle(.glass) }
        } else { self.buttonStyle(.bordered) }
    }
}

/// Several glass elements near each other share one container so they
/// blend and morph; before iOS 26 it is just the content.
struct GlassGroup<Content: View>: View {
    var spacing: CGFloat = 20
    @ViewBuilder let content: Content
    var body: some View {
        if #available(iOS 26, *) { GlassEffectContainer(spacing: spacing) { content } } else { content }
    }
}
