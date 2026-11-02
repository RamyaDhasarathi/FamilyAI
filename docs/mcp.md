# Connecting a person's own assistant (MCP)

> A read-only MCP server over the household record already exists (below): `my_day`, `decisions`, `coming_up`, `school_tomorrow`, `money_timeline`, `ask`, as the key's own person only, plus `propose`, which stages and never acts. Nothing more is planned for 20 Oct 2026 beyond reachability (a public URL) and a household-level key, which is not built because a shared key would see what no single person is allowed to.

FamilyOS is the household's shared layer. A person can connect their own assistant (Grok Bot, Claude, ChatGPT, an open-source
one) to it with a key of their own, and decide what that assistant may do. Added 15 Oct 2026.

- **Endpoint:** `POST /mcp`, JSON-RPC 2.0 over HTTP, stateless. Methods: `initialize`, `ping`, `tools/list`, `tools/call`.
  Protocol versions answered: 2026-07-28, 2025-11-25, 2025-06-18, 2025-03-26, 2024-11-05 (the client's is echoed).
- **Key:** made by an adult on **My day, My assistant** (`POST /v1/me/agents`), shown once, up to a year, revocable at once.
  `Authorization: Bearer agt_...`. Children cannot connect one.
- **Reads, as that person only:** `my_day`, `decisions`, `coming_up`, `school_tomorrow`, `money_timeline`, `ask` (cited answer).
- **Proposes, never acts:** `propose` stages a to-do, a decision on a date, handing a notice on, or marking one handled, as a card
  in Needs you (and a Telegram button). It runs only when the person confirms. A guardian's approvals (an errand, a purchase, a
  child's question) cannot be proposed.
- **Shares, only if the key was allowed to:** `share_to_family` puts a note in front of the household as an ordinary shared
  notice labelled with the assistant's name. Without that permission the tool does not exist for that key.
- **Safety:** each result says its text comes from notices and is data, not instructions; 60 calls a minute per key; every call
  is audited with the key's label and the tool (never its arguments).
- **Reachability:** a hosted assistant (Grok Bot's custom connectors) needs a public URL. Behind Tailscale only a client on the
  tailnet can reach it; a public host is on the pre-launch list.

## Testing with a real assistant, without publishing anything (15 Oct 2026)

Claude Code is an MCP client. With a throwaway scratch server (its own database, a stored master key) and a one-day assistant key,
a separate non-interactive session can use FamilyOS and nothing else, with no change to your settings:

    claude -p "<what to do>" --mcp-config mcp.json --strict-mcp-config --allowedTools "mcp__familyos" < /dev/null

where `mcp.json` is `{"mcpServers": {"familyos": {"type": "http", "url": "http://127.0.0.1:8089/mcp", "headers": {"Authorization": "Bearer agt_..."}}}}`.
The official MCP Python SDK client (v2.3.0) was also used to check the handshake and every tool.

What the first real run showed, and what changed because of it:
- It read the day, staged a proposal, and refused to claim a share it had no permission for. Good.
- It could not tell Thursday from Friday or find the time: decisions now carry `obligation_id`, `artifact_id` and `time`.
- Its first `propose` failed on the `date:` prefix of a decision id: prefixed and bare ids are both accepted.
- A notice whose text told assistants to share everyone's emails was in the data. Claude did not act on it and said so, and
  nothing was shared. The Needs you card had recommended accepting it; a notice addressed to models is now flagged, and the card
  says to dismiss it. That is one model's behaviour on one prompt, not a guarantee: keep read-only plus propose as the default.
- The activity ledger said "called a record"; it now says "Arun's assistant Claude Code read their day".

## Both ways (14 Oct 2026)

**FamilyOS → your assistant (assistant tasks).** Add your own Claude or Grok API key (`POST /v1/me/assistant-connections`; sealed under
the household key, never shown again, removable) and send it an instruction (`POST /v1/me/assistant-tasks`, answer by polling
`GET /v1/me/assistant-tasks/{id}`). FamilyOS starts the assistant with a key made for that one task: it is your own key's reach
(read and propose, never share), lasts 15 minutes, is revoked when the task ends, and unlocks one more tool, `submit_result`, which
hands the answer back once. The answer is shown as text from your assistant; nothing in it runs. A connection has a daily cap
(default 20) and the ledger records that a task was sent, done or failed, never its text.
- Claude API: Messages API with the MCP connector (`anthropic-beta: mcp-client-2025-11-20`, `mcp_servers` + `mcp_toolset`).
- Grok: xAI Responses API with a remote MCP tool (`server_url`, `authorization`).
- Both call `/mcp` from the vendor's cloud, so the server needs `FAMILYOS_MCP_PUBLIC_URL` (a public https address). Without it a task is refused up front.
- `claude_code`: runs `claude -p` on the server against `FAMILYOS_MCP_LOCAL_URL`; development only, off unless `FAMILYOS_ALLOW_LOCAL_CLAUDE_CODE=true`.

**FamilyOS → outside MCP servers (MCP client).** Register a server (`POST /v1/me/mcp-servers`), read its tool list, tick the tools
you allow, and call them yourself (`/call`). https only; the name is resolved and refused if any answer is not a public address
(loopback, private, link-local/metadata, shared, reserved); redirects are not followed; the credential is sealed; results are
size-capped, labelled untrusted, flagged if addressed to a model, and never stored. Nothing calls a tool on its own. Known gap: a
name that changes its answer between the check and the connection (DNS rebinding); the check repeats on each call to narrow it.
