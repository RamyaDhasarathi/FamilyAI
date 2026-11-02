-- Personal assistants (Grok Bot, Claude, ChatGPT, any MCP client) connect to FamilyOS with the person's own key. The key sees
-- what that person sees and nothing more; by default it can read and propose, never act, and only a key the person marked
-- "may share" can put something in front of the family. Every call is audited with the key's label.
CREATE TABLE agent_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    label TEXT NOT NULL CHECK (length(label) BETWEEN 1 AND 60),
    token_hash TEXT NOT NULL UNIQUE,
    can_share BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ
);
CREATE INDEX agent_keys_member_idx ON agent_keys (member_id, created_at DESC);
CREATE TABLE agent_calls (
    id BIGSERIAL PRIMARY KEY,
    key_id UUID NOT NULL REFERENCES agent_keys(id) ON DELETE CASCADE,
    at TIMESTAMPTZ NOT NULL DEFAULT now(),
    tool TEXT NOT NULL
);
CREATE INDEX agent_calls_key_idx ON agent_calls (key_id, at DESC);
