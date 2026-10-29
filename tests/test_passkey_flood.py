"""An unauthenticated caller can ask for sign-in challenges without limit; the open ones are capped so the table cannot be flooded."""
import pytest

from familyos import passkeys
from familyos.db import pool
from familyos.identity import Invalid
from familyos.settings import settings

ORIGIN = "http://localhost:8088"


@pytest.fixture(autouse=True)
def _origin(monkeypatch):
    monkeypatch.setattr(settings, "webauthn_origins", ORIGIN)


async def test_the_open_challenges_are_capped_and_expired_ones_make_room(database, monkeypatch):
    await pool().execute("DELETE FROM webauthn_challenges")
    monkeypatch.setattr(passkeys, "MAX_OPEN_CHALLENGES", 3)
    for _ in range(3):
        await passkeys.login_options(ORIGIN)
    with pytest.raises(Invalid, match="too many sign-ins"):
        await passkeys.login_options(ORIGIN)
    assert await pool().fetchval("SELECT count(*) FROM webauthn_challenges") == 3          # the refused one stored nothing
    await pool().execute("UPDATE webauthn_challenges SET expires_at = NOW() - interval '1 minute' WHERE ctid = (SELECT ctid FROM webauthn_challenges LIMIT 1)")
    await passkeys.login_options(ORIGIN)                                                  # an expired one was swept, so there is room again
    assert await pool().fetchval("SELECT count(*) FROM webauthn_challenges") == 3


async def test_the_flood_is_refused_over_http_too(family, monkeypatch):
    await pool().execute("DELETE FROM webauthn_challenges")
    monkeypatch.setattr(passkeys, "MAX_OPEN_CHALLENGES", 2)
    codes = [(await family.client.post("/v1/sign-in/passkey/options", headers={"Origin": ORIGIN})).status_code for _ in range(4)]
    assert codes[:2] == [200, 200] and all(c in (400, 422, 429) for c in codes[2:])
