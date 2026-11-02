-- Product search for suggestions, off until a guardian switches it on: it sends what was typed and the household's country to a
-- shop catalogue run by a third party, so it is a choice. Results are never stored.
ALTER TABLE households ADD COLUMN shop_search_enabled BOOLEAN NOT NULL DEFAULT FALSE;
