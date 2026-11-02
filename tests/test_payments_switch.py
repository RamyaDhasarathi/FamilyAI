"""Whether the family lets FamilyOS pay: off by default, a guardian's to change, and fixed off where no provider is connected."""

from familyos.settings import settings


def _rule(rules, key):
    return next(r for r in rules.json()["rules"] if r["key"] == key)


async def test_payments_are_off_and_fixed_when_no_provider_is_connected(family, monkeypatch):
    monkeypatch.setattr(settings, "payments_provider", "")
    r = _rule(await family.client.get("/v1/household/rules", headers=family.h("amma")), "payments_enabled")
    assert r["on"] is False and r["fixed"] is True and "no payment provider" in r["why_fixed"]


async def test_with_a_provider_it_is_off_until_a_guardian_turns_it_on(family, monkeypatch):
    monkeypatch.setattr(settings, "payments_provider", "crossmint")
    assert _rule(await family.client.get("/v1/household/rules", headers=family.h("amma")), "payments_enabled")["on"] is False
    r = await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"payments_enabled": True})
    assert r.status_code == 200, r.text
    rule = _rule(await family.client.get("/v1/household/rules", headers=family.h("amma")), "payments_enabled")
    assert rule["on"] is True and rule["fixed"] is False
    log = await family.client.get("/v1/audit", headers=family.h("amma"))
    assert log.status_code == 200


async def test_only_a_guardian_can_change_it_and_the_limits_are_bounded(family, monkeypatch):
    monkeypatch.setattr(settings, "payments_provider", "crossmint")
    adult = next(w for w in ("appa", "oakridge", "amma") if getattr(family, w, None) and getattr(family, w)["role"] != "guardian") if any(
        getattr(family, w, None) and getattr(family, w)["role"] != "guardian" for w in ("appa", "oakridge", "amma")) else None
    if adult:
        r = await family.client.put("/v1/household/rules", headers=family.h(adult), json={"payments_enabled": True})
        assert r.status_code in (403, 400)
    r = await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"payment_limit": 500, "payment_month_limit": 3000})
    assert r.status_code == 200, r.text
    rules = await family.client.get("/v1/household/rules", headers=family.h("amma"))
    assert _rule(rules, "payment_limit")["value"] == 500 and _rule(rules, "payment_month_limit")["value"] == 3000
    bad = await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"payment_limit": -5})
    assert bad.status_code == 422
