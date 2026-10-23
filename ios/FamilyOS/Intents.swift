// App Intents: what Siri and the Shortcuts app can ask FamilyOS to do.
// Three verbs, each the same call the screens make: ask a question, say
// what is on today, and share something into the household. The third is
// what makes a phone automation one step: a notification's text or a
// banner's screenshot goes straight in, no pasted token, no form.
import AppIntents
import Foundation

struct AskFamilyOSIntent: AppIntent {
    static var title: LocalizedStringResource = "Ask FamilyOS"
    static var description = IntentDescription("Ask a question against the family's record: a date, a fee, what a notice said.")
    static var openAppWhenRun: Bool = false

    @Parameter(title: "Question", requestValueDialog: "What do you want to ask?")
    var question: String

    static var parameterSummary: some ParameterSummary { Summary("Ask FamilyOS \(\.$question)") }

    func perform() async throws -> some IntentResult & ProvidesDialog & ReturnsValue<String> {
        guard Server.isSignedIn else { return .result(value: "", dialog: "Open FamilyOS and sign in first.") }
        let answer = try await API.shared.ask(question)
        let said = answer.answer + (answer.grounded ? "" : " (Not from the record.)")
        return .result(value: said, dialog: IntentDialog(stringLiteral: said))
    }
}

struct WhatsOnTodayIntent: AppIntent {
    static var title: LocalizedStringResource = "What's on today"
    static var description = IntentDescription("The day's dated things from the family's record, in order.")
    static var openAppWhenRun: Bool = false

    func perform() async throws -> some IntentResult & ProvidesDialog & ReturnsValue<String> {
        guard Server.isSignedIn else { return .result(value: "", dialog: "Open FamilyOS and sign in first.") }
        let brief = try await API.shared.brief()
        let cal = Calendar.current
        let today = brief.items.filter { $0.dueDate.map { cal.isDateInToday($0) } ?? false }
        // What waits on a person counts as "on today" too: a day with nothing
        // dated and eight undecided things is not an empty day.
        let waiting = brief.items.filter { $0.status == "proposed" || $0.reason == "undecided" || $0.reason == "missed" || $0.reason == "overdue" || $0.reason == "needs_you" }
        var parts: [String] = []
        if !today.isEmpty {
            parts.append(today.prefix(6).map { i in
                [i.dueTime.map(Format.clockText), i.title, i.subjectName.map { "for \($0)" }].compactMap { $0 }.joined(separator: " ")
            }.joined(separator: ". "))
        }
        if !waiting.isEmpty {
            let names = waiting.prefix(3).map(\.title).joined(separator: ", ")
            parts.append("\(waiting.count) thing\(waiting.count == 1 ? "" : "s") need\(waiting.count == 1 ? "s" : "") you: \(names)" + (waiting.count > 3 ? " and more" : ""))
        }
        let said = parts.isEmpty ? "Nothing is on today, and nothing is waiting on you." : parts.joined(separator: ". ") + "."
        return .result(value: said, dialog: IntentDialog(stringLiteral: said))
    }
}

struct ShareWithFamilyOSIntent: AppIntent {
    static var title: LocalizedStringResource = "Share with FamilyOS"
    static var description = IntentDescription("Send a photo, a PDF, a page or a piece of text into the household, tagged with a child if you say who.")
    static var openAppWhenRun: Bool = false

    @Parameter(title: "File", description: "A photo, PDF or file to share")
    var file: IntentFile?

    @Parameter(title: "Text", description: "Text or a link to share, when there is no file")
    var text: String?

    @Parameter(title: "About", description: "A child's name, to tag what is shared")
    var about: String?

    @Parameter(title: "Share with the household", default: false)
    var shared: Bool

    static var parameterSummary: some ParameterSummary {
        Summary("Share \(\.$file) with FamilyOS") {
            \.$text
            \.$about
            \.$shared
        }
    }

    func perform() async throws -> some IntentResult & ProvidesDialog {
        guard Server.isSignedIn else { return .result(dialog: "Open FamilyOS and sign in first.") }
        let result: ShareResult
        if let file {
            let type = file.type?.preferredMIMEType ?? "application/octet-stream"
            result = try await API.shared.share(data: file.data, contentType: type, tag: about, note: nil, shared: shared)
        } else if let text, !text.trimmingCharacters(in: .whitespaces).isEmpty {
            result = try await API.shared.share(data: Data(text.utf8), contentType: "text/plain", tag: about, note: nil, shared: shared)
        } else {
            return .result(dialog: "Nothing to share: give a file or some text.")
        }
        let said = result.message.isEmpty ? (result.duplicate ? "Already there." : "Received.") : result.message
        return .result(dialog: IntentDialog(stringLiteral: said))
    }
}

/// The phrases Siri answers to without any setup in the Shortcuts app.
struct FamilyOSShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: AskFamilyOSIntent(),
                    phrases: ["Ask \(.applicationName)", "Ask \(.applicationName) a question"],
                    shortTitle: "Ask", systemImageName: "sparkle")
        AppShortcut(intent: WhatsOnTodayIntent(),
                    phrases: ["What's on today in \(.applicationName)", "\(.applicationName) today"],
                    shortTitle: "Today", systemImageName: "sun.horizon")
        AppShortcut(intent: ShareWithFamilyOSIntent(),
                    phrases: ["Share with \(.applicationName)", "Send to \(.applicationName)"],
                    shortTitle: "Share", systemImageName: "square.and.arrow.up")
    }
}
