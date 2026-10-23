-- The household's rule: a notice about a child is every adult's. On by
-- default, because a school circular is both parents' business whichever
-- phone it arrived on. A guardian can turn it off for the household; and a
-- single notice made private afterwards stays private until it is tagged
-- again. The rule is applied where subjects are written, never on read.
ALTER TABLE households ADD COLUMN childrens_notices_shared BOOLEAN NOT NULL DEFAULT TRUE;
