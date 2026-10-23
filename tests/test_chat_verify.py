"""A chat answer's references are checked against the facts they point at:
a date, an amount or a name the cited fact does not carry marks the
reference unverified, and the person is told to check."""
from familyos.chat import Facts, verify_citations


def _facts(lines):
    f = Facts()
    f.lines = lines
    return f


def test_a_reference_that_carries_the_claim_passes_and_a_wrong_one_is_caught():
    facts = _facts(["[n7] notice from Apple (subscriptions, 2026-10-01): Your receipt from Apple. — 195 INR",
                    "[n20] notice from Airtel (bills, 2026-10-08): Here's your Airtel payment receipt! — 1,940.98 INR — dates in it: 2026-10-16",
                    "[n13] notice from Aachi Global (unknown, 2026-10-07): Half working day — dates in it: 2026-10-10 12:30"])
    cited = [{"ref": "n7", "text": "Your receipt from Apple."}, {"ref": "n20", "text": "Here's your Airtel payment receipt!"}, {"ref": "n13", "text": "Half working day"}]
    assert verify_citations("We paid ₹1,940.98 to Airtel last time [n20].", cited, facts) == []
    assert verify_citations("The half day ends at 12:30 PM tomorrow [n13].", cited, facts) == []
    # The Airtel bill attributed to the Apple receipt: n7 says nothing about Airtel or 16 Oct.
    assert verify_citations("The Airtel bill is due on 16 Oct [n7], and the last working day is 16 Oct [n20].", cited, facts) == ["n7"]
    # A clause with nothing checkable in it passes.
    assert verify_citations("There is a receipt [n7].", cited, facts) == []


def test_a_date_written_in_words_is_matched_to_the_iso_date_in_the_fact():
    facts = _facts(["[o2] obligation: Pay the term fee by 2026-10-20 — proposed"])
    cited = [{"ref": "o2", "text": "Pay the term fee"}]
    assert verify_citations("The term fee is due on 20 Oct [o2].", cited, facts) == []
    assert verify_citations("The term fee is due on 25 Oct [o2].", cited, facts) == ["o2"]


def test_the_household_line_can_be_cited():
    from familyos.chat import _REF
    assert _REF.findall("Varali is in class KG-1 [MEMBERS]. The bill is with Archana [HANDED] [n2].") == ["MEMBERS", "HANDED", "n2"]
