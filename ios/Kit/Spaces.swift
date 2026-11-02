// The spaces: how a notice's category sorts it into one part of life. The
// same table the console uses, so a notice is in the same space on the
// phone as on the web.
import Foundation
import SwiftUI

public enum Space: String, CaseIterable, Identifiable {
    case home, school, health, travel, money, invest
    public var id: String { rawValue }

    public var label: String {
        switch self {
        case .home: return "Home"; case .school: return "School"; case .health: return "Health"
        case .travel: return "Travel"; case .money: return "Money"; case .invest: return "Investments"
        }
    }
    public var categories: [String] {
        switch self {
        case .home: return ["home", "food", "shopping", "government", "unknown"]
        case .school: return ["school"]
        case .health: return ["medical", "insurance"]
        case .travel: return ["travel"]
        case .money: return ["bills", "banking", "subscriptions"]
        case .invest: return ["trading"]
        }
    }
    public var symbol: String {
        switch self {
        case .home: return "house"; case .school: return "graduationcap"; case .health: return "heart"
        case .travel: return "airplane"; case .money: return "banknote"; case .invest: return "chart.line.uptrend.xyaxis"
        }
    }
    public var color: Color {
        switch self {
        case .home: return Color(red: 0.49, green: 0.61, blue: 0.47)
        case .school: return Color(red: 0.36, green: 0.49, blue: 0.75)
        case .health: return Color(red: 0.80, green: 0.42, blue: 0.47)
        case .travel: return Color(red: 0.52, green: 0.45, blue: 0.75)
        case .money: return Color(red: 0.78, green: 0.60, blue: 0.27)
        case .invest: return Color(red: 0.30, green: 0.62, blue: 0.58)
        }
    }
    /// Home has no page of its own: its notices and its ledger live on Life.
    public var onLife: Bool { self == .home }

    public static func of(category: String?) -> Space {
        Space.allCases.first { $0.categories.contains(category ?? "unknown") } ?? .home
    }
    /// A notice's space: its category, or, when the sender gave none away,
    /// the child it names puts it in School.
    public static func of(_ n: InboxRow, childIds: Set<UUID>) -> Space {
        if (n.category == "unknown") && n.subjectMemberIds.contains(where: childIds.contains) { return .school }
        return of(category: n.category)
    }
}
