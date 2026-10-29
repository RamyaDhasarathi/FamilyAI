import httpx

def test_queries():
    client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=60.0)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@familyos.local", "password": "AdminPass123!"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    test_cases = [
        "Find a wireless mouse under 1000",
        "Find a backpack under 1500",
        "Find running shoes under 2500",
    ]

    for q in test_cases:
        res = client.post("/api/v1/agents/PURCHASE/chat", headers=headers, json={"message": q}).json()
        print(f"\n==========================================")
        print(f"QUERY: {q}")
        print(f"AGENT: {res['reply']}")
        cands = res.get("candidates") or []
        print(f"FOUND: {len(cands)} candidates")
        for c in cands:
            print(f"  * #{c.get('rank')} {c.get('title')} [{c.get('brand')}] - {c.get('price_amount')} {c.get('currency')}")
        assert len(cands) > 0, f"No candidates found for: {q}"

    print("\n[OK] ALL MULTI-QUERY TESTS PASSED!")

if __name__ == "__main__":
    test_queries()
