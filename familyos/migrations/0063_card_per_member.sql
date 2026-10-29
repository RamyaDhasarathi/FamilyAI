-- A saved card belongs to the guardian who saved it with the provider, because the provider ties a card to a user.
ALTER TABLE members ADD COLUMN payment_method_id TEXT;
