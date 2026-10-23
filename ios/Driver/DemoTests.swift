// A walkthrough of the app on a simulator, for a demo video: the same
// XCUITest hands as the driver, pointed at our own app, Photos and
// Shortcuts. Runs only with FAMILYOS_DEMO set, so `xcodebuild test` on the
// driver scheme never wanders into it by accident. Each stop prints a
// DEMOMARK line with the clock, so the recording can be captioned.
import XCTest

final class DemoTests: XCTestCase {
    func testWalkthrough() throws {
        continueAfterFailure = true
        let env = ProcessInfo.processInfo.environment
        guard env["FAMILYOS_DEMO"] != nil else { throw XCTSkip("set FAMILYOS_DEMO=1 (and FAMILYOS_SIGNIN_LINK, FAMILYOS_SERVER, FAMILYOS_ERRAND)") }
        let server = env["FAMILYOS_SERVER"] ?? "http://127.0.0.1:8088"
        let link = env["FAMILYOS_SIGNIN_LINK"] ?? ""
        let errand = env["FAMILYOS_ERRAND"] ?? ""
        let child = env["FAMILYOS_CHILD"] ?? "Sashreek"
        let noticeWord = env["FAMILYOS_NOTICE_WORD"] ?? "Parent-Teacher"

        func mark(_ s: String) { print("DEMOMARK \(Date().timeIntervalSince1970) \(s)"); fflush(stdout) }
        func pause(_ s: Double) { RunLoop.current.run(until: Date().addingTimeInterval(s)) }
        func launch(_ app: XCUIApplication, _ args: [String]) {
            app.launchArguments = args
            app.launch()
            if !app.wait(for: .runningForeground, timeout: 30) { print("DEMO \(app) did not come to the front"); app.activate() }
            if app.buttons["Skip"].firstMatch.waitForExistence(timeout: 1.5) { app.buttons["Skip"].firstMatch.tap(); pause(1) }
        }
        func tap(_ app: XCUIApplication, _ label: String, timeout: Double = 5) -> Bool {
            let b = app.buttons[label].firstMatch
            if b.waitForExistence(timeout: timeout) && b.isHittable { b.tap(); return true }
            let any = app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", label)).firstMatch
            if any.waitForExistence(timeout: 2) && any.isHittable { any.tap(); return true }
            print("DEMO could not tap \(label)"); return false
        }
        func tapContaining(_ app: XCUIApplication, _ text: String, timeout: Double = 5) -> Bool {
            let e = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS[c] %@", text)).firstMatch
            if e.waitForExistence(timeout: timeout) && e.isHittable { e.tap(); return true }
            print("DEMO could not tap anything containing \(text)"); return false
        }
        /// A tap that skips XCUITest's hittable check: Photos' grid says its thumbnails are not hittable, and they are.
        func tapCentre(_ e: XCUIElement) { e.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap() }
        func slowScroll(_ app: XCUIApplication, _ times: Int = 2) {
            for _ in 0..<times {
                let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.75))
                let end = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.35))
                start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.2)
                pause(1.2)
            }
        }

        // A result sheet left by an earlier intent run sits over every app until its Done is tapped.
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        func dismissSheets() {
            for _ in 0..<2 {
                let done = springboard.buttons["Done"].firstMatch
                if done.waitForExistence(timeout: 1.5) { tapCentre(done); pause(1) } else { break }
            }
        }
        dismissSheets()

        // 1. Sign in by link, land on Today.
        let app = XCUIApplication(bundleIdentifier: "com.arunmozhi.familyos")
        launch(app, link.isEmpty ? [] : ["-signinLink", link, "-server", server]); pause(8)
        mark("Today: the day as a note, what needs you, what FamilyOS is doing")
        slowScroll(app, 2); pause(1)

        // 2. Inbox, and one notice.
        _ = tap(app, "Inbox"); pause(4)
        mark("Inbox: every notice the family shared, read and dated")
        // Scroll until a school notice is on screen, then open it.
        var opened = false
        for _ in 0..<10 {
            let row = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS[c] %@", noticeWord)).firstMatch
            if row.exists && row.isHittable { row.tap(); opened = true; break }
            app.swipeUp(); pause(1.2)
        }
        if opened { pause(5); mark("A notice: its dates and asks, accepted or dismissed in a tap"); slowScroll(app, 1) }
        else { print("DEMO no row containing \(noticeWord)") }

        // 3. Family (the week ahead, the people), Ask, Settings.
        launch(app, ["-tab", "family"]); pause(5)
        mark("Family: the people, the week ahead, who holds what")
        slowScroll(app, 2)
        launch(app, ["-tab", "ask"]); pause(4)
        mark("Ask: a question over the family's own record")
        let field = app.textFields.firstMatch.exists ? app.textFields.firstMatch : app.textViews.firstMatch
        if field.waitForExistence(timeout: 4) {
            field.tap(); pause(1)
            field.typeText("What is due this week?"); pause(1)
            // Two things are labelled Send: the composer's orb and the keyboard's key. The orb is the higher one.
            let sends = app.descendants(matching: .any).matching(NSPredicate(format: "label == 'Send'")).allElementsBoundByIndex.filter { $0.isHittable }
            if let orb = sends.min(by: { $0.frame.minY < $1.frame.minY }) { orb.tap() } else { print("DEMO no Send orb") }
            pause(18)
        }
        launch(app, ["-tab", "memories"]); pause(5)
        mark("Memories: what the family kept, by the year")
        slowScroll(app, 1)
        launch(app, ["-tab", "settings"]); pause(4)
        mark("Settings: devices, Telegram, the phone's own hands, the build")
        slowScroll(app, 2)

        // 4. An errand the phone ran: the school app, read on the phone.
        if !errand.isEmpty {
            launch(app, ["-errand", errand]); pause(6)
            mark("An errand: the phone opened the school app and read it, every step pictured")
            slowScroll(app, 2)
        }

        // 5. Share from Photos through the share sheet.
        let photos = XCUIApplication(bundleIdentifier: "com.apple.mobileslideshow")
        photos.launch(); pause(5)
        if photos.buttons["Continue"].firstMatch.waitForExistence(timeout: 2) { photos.buttons["Continue"].firstMatch.tap(); pause(2) }
        mark("Share: any photo, PDF or page, from any app's share sheet")
        let thumbs = photos.images.matching(NSPredicate(format: "label BEGINSWITH[c] 'Photo'"))
        if thumbs.count > 0 { tapCentre(thumbs.element(boundBy: thumbs.count - 1)); pause(3) }
        else { print("DEMO no photo thumbnail") }
        if tap(photos, "Share") {
            pause(4)
            var fam = photos.descendants(matching: .any).matching(NSPredicate(format: "label == 'FamilyOS'")).firstMatch
            if !fam.waitForExistence(timeout: 4) {
                photos.swipeUp(); pause(2)
                fam = photos.descendants(matching: .any).matching(NSPredicate(format: "label == 'FamilyOS'")).firstMatch
            }
            if fam.waitForExistence(timeout: 3) {
                tapCentre(fam); pause(4)
                mark("Send to FamilyOS: tag a child, add a note, send")
                let picker = photos.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Child'")).firstMatch
                if picker.waitForExistence(timeout: 4) {
                    tapCentre(picker); pause(2)
                    let c = photos.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS[c] %@", child)).firstMatch
                    if c.waitForExistence(timeout: 4) { tapCentre(c) } else { print("DEMO no child \(child) in the picker") }
                    pause(2)
                }
                if tap(photos, "Send") { pause(6); mark("Sent: the notice is in the household's inbox, read in seconds") }
                _ = tap(photos, "Done", timeout: 3); pause(1)
            }
        }

        // 6. App Intents in Shortcuts, and one run.
        let sc = XCUIApplication(bundleIdentifier: "com.apple.shortcuts")
        sc.launch(); pause(6)
        mark("App Intents: Ask, What's on today, Share, as Siri phrases and Shortcuts actions")
        var tile = sc.descendants(matching: .any).matching(NSPredicate(format: "label == 'FamilyOS'")).firstMatch
        if !tile.waitForExistence(timeout: 5) { sc.swipeUp(); pause(2); tile = sc.descendants(matching: .any).matching(NSPredicate(format: "label == 'FamilyOS'")).firstMatch }
        if tile.waitForExistence(timeout: 3) {
            tile.tap(); pause(4)
            if tap(sc, "Today", timeout: 5) { pause(9); mark("Siri or a Shortcut asks what's on today; FamilyOS answers from the record"); pause(2); dismissSheets() }
        }

        // 7. Back in the app: the shared notice has arrived.
        launch(app, ["-tab", "inbox"]); pause(6)
        mark("Back in the Inbox: the shared screen is a notice now")
        slowScroll(app, 1); pause(2)
        mark("end")
    }
}
