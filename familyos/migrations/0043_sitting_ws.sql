-- The browser's own debugging socket, so the console can show the page as
-- a picture the member clicks and types into, rather than the inspector.
ALTER TABLE sign_in_sittings ADD COLUMN ws_url TEXT;
