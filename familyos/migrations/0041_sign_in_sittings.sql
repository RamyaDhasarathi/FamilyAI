-- A sign-in sitting: the member signs in to a site themselves, in a browser
-- they watch and drive; when they say they are in, what the browser holds
-- is sealed under the household key as a class-2 session, and the browser
-- is released. No password passes through FamilyOS at any point, which is
-- the only way a site with no API -- a home-services app, a school portal --
-- can ever be booked on a family's behalf.
CREATE TABLE sign_in_sittings (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    service TEXT NOT NULL,
    browser_session_id TEXT,
    live_url TEXT,
    state TEXT NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'sealed', 'abandoned')),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ
);
CREATE INDEX sign_in_sittings_open_idx ON sign_in_sittings (expires_at) WHERE state = 'open';
