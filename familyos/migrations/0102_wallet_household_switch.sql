-- Whether this household has chosen the optional family wallet (familyos/wallet/). Off until a guardian says, like payments_enabled. The column lives in
-- households so the rules page can show the switch whether or not the wallet package is loaded on this deployment.
ALTER TABLE households ADD COLUMN wallet_enabled boolean NOT NULL DEFAULT false;
