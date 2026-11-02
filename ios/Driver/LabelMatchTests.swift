import CoreGraphics
import XCTest

final class LabelMatchTests: XCTestCase {
    private func r(_ x: Double, _ y: Double, _ w: Double = 100, _ h: Double = 40) -> CGRect { CGRect(x: x, y: y, width: w, height: h) }

    func testWholeLabelOnlyNotSubstring() {
        let c = [(label: "Pay later", frame: r(0, 0)), (label: "Announcements", frame: r(0, 50))]
        XCTAssertEqual(LabelMatch.targets(for: "Pay", in: c), [])
        XCTAssertEqual(LabelMatch.targets(for: "Announce", in: c), [])
        XCTAssertEqual(LabelMatch.targets(for: "Announcements", in: c), [1])
    }

    func testCaseAndWhitespaceAreFolded() {
        let c = [(label: "  Term\u{00A0}2   Fees\n", frame: r(0, 0))]
        XCTAssertEqual(LabelMatch.targets(for: "term 2 FEES", in: c), [0])
    }

    func testTwoSeparateElementsAreTwoTargets() {
        let c = [(label: "Fees", frame: r(0, 0)), (label: "Fees", frame: r(0, 100))]
        XCTAssertEqual(LabelMatch.targets(for: "Fees", in: c).count, 2)
    }

    func testAButtonAndItsOwnTextAreOneTarget() {
        let c = [(label: "Fees", frame: r(0, 0, 200, 60)), (label: "Fees", frame: r(10, 10, 80, 20)), (label: "Fees", frame: r(0, 0, 200, 60))]
        XCTAssertEqual(LabelMatch.targets(for: "Fees", in: c), [0])
    }

    func testNothingMatchesAnEmptyLabel() {
        XCTAssertEqual(LabelMatch.targets(for: "   ", in: [(label: "", frame: r(0, 0))]), [])
    }

    func testReadingMatchesWholeWordsInsideOneLabelButNeverPartsOfWords() {
        let c = [(label: "Noah Rivera, Class 4-A", frame: r(0, 0)), (label: "Pay later", frame: r(0, 50)), (label: "Lily Rivera", frame: r(0, 100))]
        XCTAssertEqual(LabelMatch.targets(for: "Noah", in: c, containing: true), [0])
        XCTAssertEqual(LabelMatch.targets(for: "Pay", in: c, containing: true), [1])      // a whole word; for reading only
        XCTAssertEqual(LabelMatch.targets(for: "Sash", in: c, containing: true), [])        // not a piece of a word
        XCTAssertEqual(LabelMatch.targets(for: "Noah", in: c), [])                      // exact mode is unchanged
    }
}
