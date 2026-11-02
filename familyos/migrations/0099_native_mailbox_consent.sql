-- A phone app's mailbox consent is finished by the app, not by the browser that carried it to Google. The callback parks Google's
-- one-use code here and hands the app a finish token; only the signed-in member the consent began for can spend it.
ALTER TABLE google_auth_states ADD COLUMN pending_code TEXT;
ALTER TABLE google_auth_states ADD COLUMN finish_hash TEXT;
