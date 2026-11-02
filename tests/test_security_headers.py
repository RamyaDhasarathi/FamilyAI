"""The consoles are served from the API origin: headers that keep them unframed, and links that cannot run script."""
import uuid

import pytest

from tests.conftest import pdf

HEADERS = {
    "x-frame-options": "DENY",
    "content-security-policy": "frame-ancestors 'none'",
    "x-content-type-options": "nosniff",
    "cross-origin-opener-policy": "same-origin",
}


async def test_api_and_console_answers_cannot_be_framed(family):
    for path in ("/healthz", "/app/", "/v1/brief"):
        r = await family.client.get(path, headers=family.h("amma"))
        for name, value in HEADERS.items():
            if name == "content-security-policy":
                assert "frame-ancestors 'none'" in value and "frame-ancestors 'none'" in r.headers[name], path
                continue
            assert r.headers.get(name) == value, (path, name)


async def test_the_console_forbids_inline_and_foreign_scripts(family):
    r = await family.client.get("/app/")
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "'unsafe-inline'" not in csp
    assert "script-src" not in (await family.client.get("/v1/brief", headers=family.h("amma"))).headers["content-security-policy"]


async def test_the_original_file_keeps_its_own_headers_and_nothing_is_set_twice(family):
    artifact = (await family.upload("amma", pdf("a notice"), filename="Notice.pdf")).json()["artifact"]
    r = await family.client.get(f"/v1/artifacts/{artifact['id']}/original", headers=family.h("amma"))
    assert r.status_code == 200
    assert r.headers.get_list("x-content-type-options") == ["nosniff"]
    assert r.headers["cache-control"] == "private, no-store"
    assert r.headers["x-frame-options"] == "DENY"


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "http://portal.example/x", "data:text/html,hi", "//portal.example"])
async def test_a_school_portal_must_be_https(family, database, bad):
    school_id = uuid.uuid4()
    await database.execute("INSERT INTO schools (id, household_id, name) VALUES ($1, $2, 'Oakridge Global School')",
                           school_id, uuid.UUID(family.household["id"]))
    r = await family.client.put(f"/v1/household/schools/{school_id}", headers=family.h("amma"), json={"portal_url": bad})
    assert r.status_code == 422
    r = await family.client.put(f"/v1/household/schools/{school_id}", headers=family.h("amma"), json={"portal_url": "https://portal.example/x"})
    assert r.status_code == 200 and r.json()["portal_url"] == "https://portal.example/x"
