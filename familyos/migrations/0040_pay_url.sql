-- A bill's own way to pay, found in the notice it came from: the biller's
-- pay page, or a UPI intent. Kept on the obligation so "Pay" is one tap from
-- the date, the Today page and the digest. FamilyOS opens it; the person
-- pays there. Nothing here holds a card, a PIN or a login.
ALTER TABLE obligations ADD COLUMN pay_url TEXT;
