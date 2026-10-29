import httpx
import json

def test_full_offline_demo_flow():
    client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=60.0)

    # 1. Login
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@familyos.local", "password": "AdminPass123!"},
    )
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    auth_data = login_res.json()
    token = auth_data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("[1] Authenticated successfully as:", auth_data["display_name"])

    # 2. Chat with Purchase Agent
    print("[2] Sending query: 'Find noise canceling headphones under 2000'...")
    chat_res = client.post(
        "/api/v1/agents/PURCHASE/chat",
        headers=headers,
        json={"message": "Find noise canceling headphones under 2000"},
    )
    assert chat_res.status_code == 200, f"Chat failed: {chat_res.text}"
    chat_data = chat_res.json()
    task_id = chat_data["task_id"]
    print("    Purchase Agent Reply:", chat_data["reply"])
    print("    Task ID:", task_id, "| Status:", chat_data["task_status"])
    candidates = chat_data.get("candidates") or []
    print(f"    Candidates count: {len(candidates)}")
    for c in candidates:
        print(f"      - Rank #{c.get('rank')}: {c.get('title')[:60]}... | Price: {c.get('price_amount')} {c.get('currency')} | Score: {c.get('score')}")

    assert len(candidates) > 0, "No candidates returned!"
    chosen_prod = candidates[0]

    # 3. Select Candidate
    sel_res = client.post(
        f"/api/v1/purchases/{task_id}/select",
        headers=headers,
        json={"product_id": chosen_prod["id"]},
    )
    assert sel_res.status_code == 200, f"Select failed: {sel_res.text}"
    print(f"[3] Selected candidate: '{chosen_prod['title'][:40]}...' Status: {sel_res.json()['status']}")

    # 4. Prepare Execution
    prep_res = client.post(f"/api/v1/purchases/{task_id}/prepare-execution", headers=headers)
    assert prep_res.status_code == 200, f"Prepare failed: {prep_res.text}"
    prep_data = prep_res.json()
    instruction_id = prep_data["instruction_id"]
    print(f"[4] Prepared Execution Instruction: {instruction_id} | Status: {prep_data['status']}")

    # 5. Execute Instruction
    exec_res = client.post(f"/api/v1/mobile-use/instructions/{instruction_id}/execute", headers=headers)
    assert exec_res.status_code == 200, f"Execute failed: {exec_res.text}"
    exec_data = exec_res.json()
    print("[5] Execution completed successfully!")
    print("    Engine:", exec_data.get("engine"))
    print("    Payment Boundary Enforced:", exec_data.get("payment_boundary_enforced"))
    print("    Notice:", exec_data.get("notice"))
    print(f"    Action Steps Executed: {len(exec_data.get('action_trace', []))}")
    for s in exec_data.get("action_trace", []):
        print(f"      Step {s.get('step')}: {s.get('action')} -> {s.get('element')} ({s.get('status')}) | {s.get('details')}")

    print("\n[OK] ALL CORE LOGIC AND API FLOW CHECKS PASSED PERFECTLY!")

if __name__ == "__main__":
    test_full_offline_demo_flow()
