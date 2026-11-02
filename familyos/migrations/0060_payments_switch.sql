-- Whether the family lets FamilyOS pay on its behalf at all. Off until a guardian says.
-- Even when on, nothing is paid without a guardian approving that one purchase; these are
-- the ceilings a single purchase and a calendar month may not pass, in the household's currency.
ALTER TABLE households
    ADD COLUMN payments_enabled boolean NOT NULL DEFAULT false,
    ADD COLUMN payment_limit INTEGER NOT NULL DEFAULT 2000 CHECK (payment_limit BETWEEN 0 AND 100000),
    ADD COLUMN payment_month_limit INTEGER NOT NULL DEFAULT 10000 CHECK (payment_month_limit BETWEEN 0 AND 1000000);
