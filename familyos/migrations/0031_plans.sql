-- A plan: the open-ended task, in the shape this system can keep honest.
--
-- "Plan a week in Switzerland in the Diwali break, under four lakh" is not a
-- notice and proposes nothing on its own. What FamilyOS can do with it is
-- what it already knows how to do: write the itinerary with the household's
-- own dates in view, hold a handful of candidate bookings as public pages
-- it reads and re-reads without signing in, turn the legwork into to-dos
-- with names and dates, and wait for the confirmation mail to arrive through
-- the mailbox like any other notice.
--
-- What it does not do is book. Booking is a payment and a passport number,
-- and both stay in the family's hands by design. "Open to book" is a link.
CREATE TABLE plans (
    id UUID PRIMARY KEY,
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    created_by UUID REFERENCES members(id) ON DELETE SET NULL,
    title TEXT NOT NULL CHECK (length(btrim(title)) BETWEEN 1 AND 160),
    brief TEXT NOT NULL CHECK (length(brief) <= 2000),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'done', 'dropped')),
    starts_on DATE,
    ends_on DATE,
    budget_amount NUMERIC(12, 2),
    budget_currency TEXT,
    summary TEXT,
    -- [{"day": 1, "date": "2026-10-20", "title": "Fly to Zurich", "notes": "..."}]
    itinerary JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- [{"id": "...", "kind": "flight|stay|transport|activity|insurance|visa", "label": "...",
    --   "provider": "...", "url": "...", "estimate": 84000, "currency": "INR", "note": "...",
    --   "watch_id": null, "chosen": false, "booked_at": null}]
    options JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX plans_household_idx ON plans (household_id, status, created_at DESC);

-- A to-do can belong to a plan: the legwork, with the plan's dates.
ALTER TABLE todos ADD COLUMN plan_id UUID REFERENCES plans(id) ON DELETE SET NULL;
CREATE INDEX todos_plan_idx ON todos (plan_id) WHERE plan_id IS NOT NULL;
