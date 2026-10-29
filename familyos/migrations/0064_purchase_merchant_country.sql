-- The provider wants the merchant's country (two letters) to scope an allowance.
ALTER TABLE purchases ADD COLUMN merchant_country CHAR(2);
