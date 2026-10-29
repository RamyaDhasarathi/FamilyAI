// The first-run checklist (familyos/onboarding.py): sign in, name the home,
// add the family, a channel, a mailbox, make it private. Each step is read off the household; only
// a guardian's choices are stored, and nothing here does anything on its own.
import Foundation

public struct SetupStep: Codable, Identifiable, Hashable {
    public let key: String
    public let title: String
    public let detail: String?
    public let done: Bool
    public let optional: Bool
    /// For the private step: the family already holds the key (not merely skipped).
    public let on: Bool?
    public var id: String { key }
}

public struct SetupStatus: Codable, Hashable {
    public let steps: [SetupStep]
    public let done: Int
    public let total: Int
    public let complete: Bool
    public let dismissed: Bool
    /// True only for a guardian with something left and the checklist not hidden.
    public let show: Bool
    /// True until the name step is answered: a brand-new home that has not been through the first-run screens.
    public let wizard: Bool?
}

extension API {
    public func onboarding() async throws -> SetupStatus { try await json("GET", "/household/onboarding") }
    /// `named`, `skip_channel`, `skip_mail`, `skip_private` or `dismissed`; the answer is the checklist as it now stands.
    public func answerOnboarding(_ choice: String) async throws -> SetupStatus { try await json("POST", "/household/onboarding/\(choice)") }
}
