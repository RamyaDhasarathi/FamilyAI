// Walks the FamilyOS app itself on a real phone and prints what each screen says, in reading order, so a person
// who cannot hold the phone can see whether the screens are right. Runs only with FAMILYOS_SELFCHECK=1:
//   TEST_RUNNER_FAMILYOS_SELFCHECK=1 xcodebuild test -scheme FamilyOSDriver -destination 'id=<udid>' -only-testing:FamilyOSDriver/SelfCheckTests
// The app must already be signed in. It taps only to open screens and go back; it never presses a button that changes anything.
import XCTest

final class SelfCheckTests: XCTestCase {
    private let app = XCUIApplication()

    /// Every visible label on the screen, top to bottom, scrolling down until nothing new shows up.
    private func readScreen(_ name: String, scrolls: Int = 8) -> [String] {
        var seen: [String] = []
        for step in 0...scrolls {
            let els = app.descendants(matching: .any).allElementsBoundByIndex
            let rows: [(CGFloat, String)] = els.compactMap { el in
                guard el.exists, el.isHittable || el.elementType == .staticText, !el.label.isEmpty, el.frame.height > 0,
                      el.frame.minY >= 0, el.frame.minY < app.frame.height else { return nil }
                return (el.frame.minY, el.label.replacingOccurrences(of: "\n", with: " "))
            }.sorted { $0.0 < $1.0 }
            var added = 0
            for (_, label) in rows where !seen.contains(label) { seen.append(label); added += 1 }
            if step > 0 && added == 0 { break }
            app.swipeUp()
        }
        print("SCREEN [\(name)]")
        seen.forEach { print("  \($0.prefix(110))") }
        return seen
    }

    private func scrollTop() { for _ in 0..<6 { app.swipeDown() } }

    func testWalk() throws {
        guard ProcessInfo.processInfo.environment["FAMILYOS_SELFCHECK"] == "1" else { throw XCTSkip("set FAMILYOS_SELFCHECK=1") }
        continueAfterFailure = true
        app.launch()
        sleep(3)
        let launch = readScreen("Launch", scrolls: 1)
        XCTAssertFalse(launch.isEmpty, "nothing on screen")
        let signedOut = launch.contains { $0.localizedCaseInsensitiveContains("Continue with Google") }
        print("SIGNED-IN \(!signedOut)")
        XCTAssertFalse(signedOut, "the app asked for sign-in: the Keychain did not survive")

        // Settings: a tab, a button anywhere, or the last tab under "More".
        let anySettings = app.descendants(matching: .any).matching(NSPredicate(format: "label == 'Settings and profile' OR label == 'Settings'")).firstMatch
        if app.tabBars.buttons["Settings"].exists { app.tabBars.buttons["Settings"].tap() }
        else if anySettings.exists { anySettings.tap() }
        else if app.tabBars.buttons["More"].exists { app.tabBars.buttons["More"].tap(); sleep(1); app.staticTexts["Settings"].firstMatch.tap() }
        sleep(2)
        let settings = readScreen("Settings")
        let order = ["Your profile", "People", "Privacy and security", "Connections", "Notifications", "Your day and home", "About this phone", "Sign out"]
        var at = -1
        for want in order {
            if let i = settings.firstIndex(where: { $0.localizedCaseInsensitiveContains(want) }) {
                XCTAssertGreaterThan(i, at, "\(want) is out of order"); at = i
                print("ORDER ok \(want) @\(i)")
            } else { print("ORDER missing \(want)"); XCTFail("\(want) not found in Settings") }
        }

        scrollTop()
        // Profile.
        if app.buttons["Your profile"].firstMatch.exists || app.staticTexts["Your profile"].exists {
            (app.buttons["Your profile"].exists ? app.buttons["Your profile"] : app.staticTexts["Your profile"]).firstMatch.tap()
            sleep(2); _ = readScreen("Profile", scrolls: 5)
            app.navigationBars.buttons.firstMatch.tap(); sleep(1)
        } else { XCTFail("Your profile row not reachable") }

        // Connections → WhatsApp reading.
        for _ in 0..<6 where !app.staticTexts["WhatsApp reading"].exists { app.swipeUp() }
        if app.staticTexts["WhatsApp reading"].exists || app.buttons["WhatsApp reading"].exists {
            (app.buttons["WhatsApp reading"].exists ? app.buttons["WhatsApp reading"] : app.staticTexts["WhatsApp reading"]).firstMatch.tap()
            sleep(2); let wa = readScreen("WhatsApp reading", scrolls: 5)
            print("WHATSAPP images=\(app.images.count) qrLike=\(app.images.allElementsBoundByIndex.filter { $0.frame.width > 120 }.count)")
            XCTAssertFalse(wa.isEmpty)
        } else { print("WHATSAPP row not shown (feature switch off for this server?)") }
    }
}
