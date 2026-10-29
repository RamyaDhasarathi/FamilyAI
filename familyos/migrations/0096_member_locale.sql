-- A person's own zone and language, over the household's. Someone who lives or works in another country than the household (a parent in Dubai,
-- the rest in Chennai) has their own day and their own words. NULL means the household's. The household also gets a language: IANA/BCP 47
-- tag, 'en' until someone says otherwise. Every stored time stays UTC (timestamptz); the zone is for working out a day and for showing.
ALTER TABLE members ADD COLUMN timezone TEXT, ADD COLUMN language TEXT;
ALTER TABLE households ADD COLUMN language TEXT NOT NULL DEFAULT 'en';
