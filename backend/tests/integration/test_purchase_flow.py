"""End-to-end integration tests for the complete Purchase Agent -> Mobile Use workflow."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_full_purchase_workflow_to_simulation(client: AsyncClient, bootstrapped_admin, admin_headers):
    """Scenario A + D: Complete vertical flow from chat to simulated mobile execution."""
    # 1. Chat with Purchase Agent
    chat_resp = await client.post(
        "/api/v1/agents/PURCHASE/chat",
        headers=admin_headers,
        json={"message": "Find a wireless mouse under 1500"},
    )
    assert chat_resp.status_code == 200, chat_resp.text
    chat_data = chat_resp.json()
    assert chat_data["agent_type"] == "PURCHASE"
    assert chat_data["task_id"] is not None
    assert len(chat_data["candidates"]) > 0

    task_id = chat_data["task_id"]
    selected_cand = chat_data["candidates"][0]

    # 2. Select Candidate
    sel_resp = await client.post(
        f"/api/v1/purchases/{task_id}/select",
        headers=admin_headers,
        json={"product_id": selected_cand["id"]},
    )
    assert sel_resp.status_code == 200, sel_resp.text
    assert sel_resp.json()["status"] == "OPTION_SELECTED"

    # 3. Prepare Execution Instruction
    prep_resp = await client.post(
        f"/api/v1/purchases/{task_id}/prepare-execution",
        headers=admin_headers,
    )
    assert prep_resp.status_code == 200, prep_resp.text
    prep_data = prep_resp.json()
    assert "instruction_id" in prep_data

    instruction_id = prep_data["instruction_id"]

    # 4. If approval was required, approve it
    if prep_data.get("approval_required"):
        approval_id = prep_data["approval_id"]
        appr_resp = await client.post(
            f"/api/v1/approvals/{approval_id}/approve",
            headers=admin_headers,
            json={"reason": "Approved by admin for test"},
        )
        assert appr_resp.status_code == 200

    # 5. Execute instruction via Mobile Use Agent
    exec_resp = await client.post(
        f"/api/v1/mobile-use/instructions/{instruction_id}/execute",
        headers=admin_headers,
    )
    assert exec_resp.status_code == 200, exec_resp.text
    exec_data = exec_resp.json()
    assert exec_data["status"] == "SUCCEEDED"
    assert exec_data["is_simulated"] is True
    assert "no real purchase was made" in exec_data["message"]

    # 6. Verify audit trail logged the events
    audit_resp = await client.get("/api/v1/governance/audit", headers=admin_headers)
    assert audit_resp.status_code == 200
    events = audit_resp.json()
    assert len(events) >= 2
    actions = [e["action"] for e in events]
    assert any("mobile_use.instruction.execute" in a for a in actions)


async def test_travel_agent_placeholder_safely_declares_unimplemented(client: AsyncClient, admin_headers):
    """Travel Agent endpoint returns a clear 503 stating it is planned."""
    resp = await client.post(
        "/api/v1/agents/TRAVEL/chat",
        headers=admin_headers,
        json={"message": "Book flight to Tokyo"},
    )
    assert resp.status_code == 503
    data = resp.json()
    assert data["error"]["code"] == "AGENT_UNAVAILABLE"
    assert "planned but is not implemented" in data["error"]["message"].lower()
