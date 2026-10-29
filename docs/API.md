# Family OS — REST API Specification

This document defines the complete REST API interface for Family OS (`v0.1.0`).

All API routes (except `/health`) are prefixed with `/api/v1`.

---

## 1. Authentication & Common Headers

### Request Headers
| Header | Type | Required | Description |
|---|---|---|---|
| `Authorization` | `string` | Protected endpoints | Bearer JWT token: `Bearer <access_token>` |
| `Content-Type` | `string` | Yes (for JSON bodies) | `application/json` (or `multipart/form-data` for audio upload) |
| `X-Correlation-ID` | `string` | Optional | Client-generated UUID tracking request trace. Returned in all responses. |

### Response Error Format
All standard application errors return structured JSON with consistent error codes:

```json
{
  "code": "FGP_ACCESS_DENIED",
  "message": "Permission denied for action: purchase.execution/execute",
  "correlation_id": "c1f7b8a2-1111-4444-9999-abcdef123456",
  "details": {
    "reason_code": "NO_GRANT"
  }
}
```

Common Error Codes:
- `AUTHENTICATION_REQUIRED` (401)
- `INVALID_CREDENTIALS` (401)
- `FGP_ACCESS_DENIED` (403)
- `RESOURCE_NOT_FOUND` (404)
- `APPROVAL_REQUIRED` (403)
- `IDEMPOTENT_OPERATION_EXISTS` (409)
- `AGENT_UNAVAILABLE` (503)
- `VALIDATION_ERROR` (422)

---

## 2. Health & System Status

### `GET /health`
Liveness probe.
- **Auth:** None
- **Response 200:**
```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

### `GET /api/v1/system/status`
Comprehensive readiness check for database, LLM provider, and services. Never leaks API keys or secrets.
- **Auth:** Bearer Token
- **Response 200:**
```json
{
  "status": "operational",
  "version": "0.1.0",
  "database": "connected",
  "llm_provider": {
    "name": "mock",
    "available": true,
    "is_mock": true
  },
  "product_provider": "development_catalogue",
  "stt_provider": "disabled",
  "tts_provider": "disabled"
}
```

---

## 3. Authentication & Account Management

### `POST /api/v1/auth/bootstrap`
One-time bootstrap endpoint for setting up the primary family and administrator. Fails if a family already exists.
- **Request Body:**
```json
{
  "bootstrap_token": "dev-bootstrap-token-change-in-production",
  "email": "admin@familyos.local",
  "password": "AdminPass123!",
  "display_name": "Family Admin",
  "family_name": "The Miller Family"
}
```
- **Response 200:** Returns `TokenResponse` with JWT access & refresh tokens.

### `POST /api/v1/auth/login`
Authenticates a family member with Argon2id password verification.
- **Request Body:**
```json
{
  "email": "admin@familyos.local",
  "password": "AdminPass123!"
}
```
- **Response 200:**
```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "user_id": "usr_uuid",
  "display_name": "Family Admin",
  "family_id": "fam_uuid",
  "membership_id": "mem_uuid",
  "family_role": "ADMIN"
}
```

### `POST /api/v1/auth/refresh`
Issues a new access token using a valid refresh token.
- **Request Body:** `{"refresh_token": "..."}`
- **Response 200:** `{"access_token": "...", "token_type": "bearer"}`

### `GET /api/v1/auth/me`
Retrieves current session and family profile information.
- **Auth:** Bearer Token
- **Response 200:**
```json
{
  "user_id": "usr_uuid",
  "email": "admin@familyos.local",
  "display_name": "Family Admin",
  "is_active": true,
  "family_id": "fam_uuid",
  "membership_id": "mem_uuid",
  "family_role": "ADMIN",
  "family_name": "The Miller Family"
}
```

---

## 4. Family & Membership Management

### `GET /api/v1/families/current`
Returns active family details.
- **Auth:** Bearer Token

### `GET /api/v1/families/current/members`
Lists all members in the current family.
- **Auth:** Bearer Token

### `POST /api/v1/families/current/members`
Adds a new member to the family. Enforces `ADMIN` role check.
- **Auth:** Bearer Token (`ADMIN`)
- **Request Body:**
```json
{
  "email": "child@familyos.local",
  "password": "ChildPass123!",
  "display_name": "Alice Miller",
  "role": "CHILD_MEMBER"
}
```

---

## 5. Family Governance Platform (FGP)

### `GET /api/v1/governance/permissions`
Returns all active permission grants within the family.
- **Auth:** Bearer Token (`ADMIN`)

### `GET /api/v1/governance/members/{membership_id}/permissions`
Retrieves grants for a specific member.
- **Auth:** Bearer Token (Self or `ADMIN`)

### `POST /api/v1/governance/permissions`
Creates a new fine-grained permission grant.
- **Auth:** Bearer Token (`ADMIN`)
- **Request Body:**
```json
{
  "subject_membership_id": "mem_uuid",
  "resource": "purchase.execution",
  "action": "execute",
  "effect": "ALLOW",
  "approval_required": true,
  "constraints_json": {
    "max_spend": 2000,
    "currency": "INR"
  }
}
```

### `PATCH /api/v1/governance/permissions/{permission_id}`
Updates an existing grant (toggles approval requirements or effect).
- **Auth:** Bearer Token (`ADMIN`)

### `DELETE /api/v1/governance/permissions/{permission_id}`
Soft-deletes a permission grant.
- **Auth:** Bearer Token (`ADMIN`)

### `GET /api/v1/governance/audit`
Retrieves immutable audit trail entries (last 100).
- **Auth:** Bearer Token (`ADMIN`)

---

## 6. Agents & Conversations

### `GET /api/v1/agents`
Returns registry of known agents.
- **Response 200:**
```json
[
  {
    "type": "PURCHASE",
    "name": "Purchase Agent",
    "status": "available",
    "description": "Assists with product discovery, comparison, and purchase preparation."
  },
  {
    "type": "TRAVEL",
    "name": "Travel Agent",
    "status": "planned",
    "description": "Travel planning and booking assistance (planned for future release)."
  }
]
```

### `POST /api/v1/agents/{agent_type}/chat`
Main conversation endpoint. Dispatches to the corresponding agent.
- Calling with `agent_type=TRAVEL` returns `503 Service Unavailable` with message: *"Travel Agent is planned but is not implemented in this release."*
- **Auth:** Bearer Token
- **Request Body:**
```json
{
  "conversation_id": null,
  "message": "Find me a wireless mouse under 1500 INR",
  "task_id": null
}
```
- **Response 200:**
```json
{
  "conversation_id": "conv_uuid",
  "message_id": "msg_uuid",
  "agent_type": "PURCHASE",
  "reply": "I found 5 wireless mice matching your criteria...",
  "task_id": "task_uuid",
  "task_status": "RECOMMENDATION_READY",
  "structured_response": {
    "response_type": "recommendation",
    "purchase_intent": {
      "category": "mouse",
      "budget_amount": 1500,
      "currency": "INR"
    }
  },
  "candidates": [
    {
      "id": "cand_uuid",
      "title": "Logitech M235 Wireless Mouse",
      "brand": "Logitech",
      "price_amount": 895.0,
      "currency": "INR",
      "source_type": "DEVELOPMENT_CATALOGUE",
      "score": 85.0,
      "rank": 1
    }
  ],
  "available_actions": ["SELECT_PRODUCT", "REFINE_SEARCH", "CANCEL"],
  "correlation_id": "...",
  "is_development_data": true
}
```

---

## 7. Purchase Tasks & Execution Flow

### `GET /api/v1/purchases`
Lists all purchase tasks initiated by the requesting user.

### `GET /api/v1/purchases/{task_id}`
Retrieves task details and current status.

### `GET /api/v1/purchases/{task_id}/candidates`
Retrieves product comparison candidates scored for this task.

### `POST /api/v1/purchases/{task_id}/select`
Selects a candidate product for purchase.
- **Request Body:** `{"product_id": "cand_uuid"}`

### `POST /api/v1/purchases/{task_id}/prepare-execution`
Prepares a `MobileUseInstruction`. Checks FGP policy. If policy requires approval, creates an `ApprovalRequest` and sets status to `AWAITING_APPROVAL`. If approved, sets status to `EXECUTION_PREPARED`.

### `POST /api/v1/mobile-use/instructions/{instruction_id}/execute`
Executes an authorized instruction via the Mobile Use Agent.
- **Auth:** Bearer Token
- **Response 200:**
```json
{
  "instruction_id": "inst_uuid",
  "status": "SUCCEEDED",
  "action_type": "SIMULATE_EXECUTION",
  "result": {
    "simulation": true,
    "message": "Simulation completed — no real purchase was made.",
    "product_title": "Logitech M235 Wireless Mouse",
    "amount": 895.0,
    "currency": "INR"
  }
}
```

---

## 8. Voice Interaction

### `POST /api/v1/voice/transcribe`
Uploads audio recorded on the mobile device for transcription.
- **Content-Type:** `multipart/form-data`
- **Form Fields:** `file` (audio binary, e.g. `.m4a`, `.wav`, max 10MB)
- **Response 200 (When STT disabled / mock):**
```json
{
  "text": null,
  "is_available": false,
  "message": "Speech-to-text is not configured. Use text input."
}
```

### `POST /api/v1/voice/synthesize`
Generates spoken audio output from text.
- **Request Body:** `{"text": "Your order has been simulated."}`
- **Response 200:** `{"audio_url": null, "is_available": false}`
