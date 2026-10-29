"""A password-protected PDF: the first real mailbox produced one within a
minute, a bank statement, and the reader failed five times and told nobody.
It is not a failure. It is a document the family would have to unlock for
us, which is their decision, so it is read once, said plainly, and left."""
import pytest

from familyos.extraction import parse, pipeline, sandbox


def _locked_pdf(password: str = "ABCDE1234F") -> bytes:
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Statement for September. Amount due Rs 3,420 by 12 October.")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password)
    doc.close()
    return data


def test_the_parser_names_a_locked_pdf_instead_of_raising():
    doc = parse.parse(_locked_pdf(), "application/pdf")
    assert doc.pages == [] and parse.LOCKED in doc.notes


async def test_the_sandbox_returns_it_as_a_document_not_a_failure():
    doc = await sandbox.parse_isolated(_locked_pdf(), "application/pdf")
    assert parse.LOCKED in doc.notes and doc.char_count == 0


async def test_the_extraction_says_why_in_the_familys_words():
    doc = parse.parse(_locked_pdf(), "application/pdf")
    x = await pipeline.extract(doc, None, pipeline.make_extractor("rules"))
    assert x.actionable is False
    assert "password-protected" in x.non_actionable_reason and "PAN" in x.non_actionable_reason
    assert x.claims == []


async def test_a_locked_statement_lands_in_the_inbox_as_information_with_the_reason(family, database, monkeypatch):
    from familyos.settings import settings
    monkeypatch.setattr(settings, "extractor", "rules")
    from tests.test_extraction import _run_extraction
    r = await family.upload("amma", _locked_pdf(), filename="statement.pdf", visibility="shared")
    artifact_id = r.json()["artifact"]["id"]
    assert (await _run_extraction(database, artifact_id))["status"] == "succeeded"
    row = (await family.client.get("/v1/inbox", headers=family.h("amma"))).json()[0]
    assert row["state"] == "info" and row["headline"] == "statement.pdf"
    assert "password-protected" in row["reason"]
