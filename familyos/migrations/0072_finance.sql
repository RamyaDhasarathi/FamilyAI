-- Household finance, the coordination layer above the accounts (never a bank): monthly budgets by category, purchases
-- and warranties with their return and warranty dates, savings goals with what has been put in, bills split between adults
-- with who has settled, and a per-member limit on what one person may ask to buy.
CREATE TABLE budgets (
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    category TEXT NOT NULL CHECK (length(category) BETWEEN 1 AND 40),
    monthly_limit NUMERIC(14, 2) NOT NULL CHECK (monthly_limit > 0),
    currency TEXT NOT NULL DEFAULT 'INR',
    PRIMARY KEY (household_id, category, currency)
);
CREATE TABLE warranties (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 160),
    merchant TEXT,
    purchased_on DATE,
    return_by DATE,
    warranty_until DATE,
    artifact_id UUID REFERENCES input_artifacts(id) ON DELETE SET NULL,
    created_by UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ
);
CREATE TABLE savings_goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 120),
    target_amount NUMERIC(14, 2) NOT NULL CHECK (target_amount > 0),
    currency TEXT NOT NULL DEFAULT 'INR',
    by_date DATE,
    created_by UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ
);
CREATE TABLE goal_contributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID NOT NULL REFERENCES savings_goals(id) ON DELETE CASCADE,
    member_id UUID REFERENCES members(id) ON DELETE SET NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount <> 0),
    note TEXT,
    at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE bill_splits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 160),
    amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    currency TEXT NOT NULL DEFAULT 'INR',
    paid_by UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE bill_split_shares (
    split_id UUID NOT NULL REFERENCES bill_splits(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount >= 0),
    settled_at TIMESTAMPTZ,
    PRIMARY KEY (split_id, member_id)
);
ALTER TABLE members ADD COLUMN payment_limit NUMERIC(14, 2) CHECK (payment_limit IS NULL OR payment_limit >= 0);
