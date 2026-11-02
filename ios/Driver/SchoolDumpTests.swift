// Diagnostic for an app the driver reads (a school's parent app): opens it, selects one child, scrolls down the child's page, and
// prints every element's type, label and whether it is hittable, so a tap that finds nothing can be explained. Read-only:
// the only tap is on the child. Runs only with FAMILYOS_DUMP_BUNDLE set.
//   TEST_RUNNER_FAMILYOS_DUMP_BUNDLE=<bundle id> TEST_RUNNER_FAMILYOS_DUMP_CHILD=<first name> xcodebuild test ... -only-testing:FamilyOSDriver/SchoolDumpTests
import XCTest

final class SchoolDumpTests: XCTestCase {
    func testDump() throws {
        let env = ProcessInfo.processInfo.environment
        guard let bundle = env["FAMILYOS_DUMP_BUNDLE"] else { throw XCTSkip("set FAMILYOS_DUMP_BUNDLE") }
        let app = XCUIApplication(bundleIdentifier: bundle)
        app.launch()
        sleep(8)
        var seen = Set<String>()
        func dump(_ title: String) {
            print("DUMP [\(title)]")
            for kind: XCUIElement.ElementType in [.button, .cell, .staticText, .link, .other, .image] {
                let q = app.descendants(matching: kind)
                for i in 0..<min(q.count, 120) {
                    let e = q.element(boundBy: i)
                    guard e.exists, !e.label.isEmpty else { continue }
                    let line = "  \(kind.rawValue) hit=\(e.isHittable ? 1 : 0) y=\(Int(e.frame.minY)) \(e.label.replacingOccurrences(of: "\n", with: " ").prefix(Int(env["FAMILYOS_DUMP_WIDTH"] ?? "70") ?? 70))"
                    if seen.insert(line).inserted { print(line) }
                }
            }
        }
        dump("launch")
        // FAMILYOS_DUMP_PATH="Noah,Announcement": taps, in order, the one hittable element whose label contains each word.
        // FAMILYOS_DUMP_SWIPES: how many swipes up to dump afterwards.
        for word in (env["FAMILYOS_DUMP_PATH"] ?? env["FAMILYOS_DUMP_CHILD"] ?? "").split(separator: ",").map(String.init) where !word.isEmpty {
            let hit = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS[c] %@", word)).allElementsBoundByIndex.first { $0.isHittable }
            print("TAP \(word): \(hit.map { "\($0.elementType.rawValue) '\($0.label.prefix(60))'" } ?? "none hittable")")
            hit?.tap(); sleep(4)
            dump("after tapping \(word)")
        }
        for n in 0..<(Int(env["FAMILYOS_DUMP_SWIPES"] ?? "0") ?? 0) {
            app.swipeUp(); sleep(1)
            dump("after swipe \(n + 1)")
        }
    }
}
