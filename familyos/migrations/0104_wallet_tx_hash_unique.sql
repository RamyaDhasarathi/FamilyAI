-- A transaction hash is reported for one transfer only: two approved transfers with the same payee and amount could otherwise both be settled by one
-- transaction on the chain. Partial, so every transfer that has no hash yet is unaffected.
CREATE UNIQUE INDEX wallet_transfers_tx_hash_idx ON wallet_transfers (tx_hash) WHERE tx_hash IS NOT NULL;
