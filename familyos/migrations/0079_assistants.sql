-- FamilyOS sending a task to a person's own assistant and getting an answer back, and FamilyOS using an outside MCP server.
-- A connection is a person's own Claude or Grok API key (sealed under the household key) or the local Claude Code on the server's
-- host. A task is an instruction the person wrote; the answer is shown to them as a card and never acts. External sources are
-- MCP servers a person registers; only tools they have allowed can be called, and what comes back is untrusted data.
CREATE TABLE assistant_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (provider IN ('claude', 'grok', 'claude_code')),
    label TEXT NOT NULL CHECK (length(label) BETWEEN 1 AND 60),
    model TEXT,
    sealed_api_key BYTEA,
    daily_cap SMALLINT NOT NULL DEFAULT 20 CHECK (daily_cap BETWEEN 1 AND 200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ
);
CREATE TABLE assistant_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    connection_id UUID NOT NULL REFERENCES assistant_connections(id) ON DELETE CASCADE,
    instruction TEXT NOT NULL CHECK (length(instruction) BETWEEN 3 AND 1500),
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    result TEXT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    seen_at TIMESTAMPTZ
);
CREATE INDEX assistant_tasks_member_idx ON assistant_tasks (member_id, created_at DESC);
CREATE TABLE external_mcp (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    label TEXT NOT NULL CHECK (length(label) BETWEEN 1 AND 60),
    url TEXT NOT NULL,
    sealed_auth BYTEA,
    allowed_tools TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ
);
-- A key made for one task (minutes long, revoked when the task ends) lets the assistant hand its answer back with submit_result.
ALTER TABLE agent_keys ADD COLUMN task_id UUID REFERENCES assistant_tasks(id) ON DELETE CASCADE;
