// Which on-screen elements a taught label names. The server's contract (familyos/execution/phone.py, click_text): tap the one
// element whose whole visible label is the text, ignoring case and runs of whitespace; none is "not there", more than one is
// refused. Never the first of several, and never an element that merely contains the words ("Pay" inside "Pay later").
import CoreGraphics
import Foundation

enum LabelMatch {
    /// Whitespace (including non-breaking spaces and newlines) folded to single spaces, trimmed, lower-cased.
    static func normalise(_ s: String) -> String {
        s.split(whereSeparator: { $0.isWhitespace || $0 == "\u{00A0}" }).joined(separator: " ").lowercased()
    }

    /// The distinct things on the screen the label names. `candidates` are (label, frame) pairs in screen order. A button and the
    /// text inside it, or a cell and its one label, carry the same words in nested frames: that is one target, not two, so a frame
    /// inside another matching frame is dropped. Returns the indices of the targets, outermost first-seen.
    static func targets(for text: String, in candidates: [(label: String, frame: CGRect)], containing: Bool = false) -> [Int] {
        let want = normalise(text)
        guard !want.isEmpty else { return [] }
        // `containing` is for reading, never for committing: the words as whole words somewhere in the label ("Noah" in
        // "Noah Rivera, 4-A"), still only when exactly one thing on the screen says them. "Pay" is never inside "Pay later".
        let hits = candidates.indices.filter { i in
            let label = normalise(candidates[i].label)
            return containing ? (" " + label + " ").contains(" " + want + " ") : label == want
        }
        return hits.filter { i in
            !hits.contains { j in j != i && candidates[j].frame.contains(candidates[i].frame)
                && (candidates[j].frame != candidates[i].frame || j < i) }
        }
    }
}
