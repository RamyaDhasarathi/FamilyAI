-- Where the member watches and drives a sitting, supplied by whatever browser
-- is configured. A separate migration rather than an edit to 0019, which has
-- already run: a migration file changed after it is applied leaves every
-- database that saw the old version quietly wrong, and nothing detects it.
ALTER TABLE harvests ADD COLUMN live_url TEXT;
