# The optional family wallet (`familyos/wallet/`)

Built 23 Oct 2026. **Test networks only.** `settings.py` refuses any chain id that is not Base Sepolia (84532) or Ethereum Sepolia (11155111); a mainnet needs a legal review of virtual-asset rules in the countries served first. No key, seed or signing capability exists on the server: `eth-account` is used only to *recover* who signed.

## Two switches, both off

1. **The deployment**: `FAMILYOS_WALLET_ENABLED=true`.
2. **The household**: the "Family wallet (test network only)" switch on the Rules page, guardians only, audited like every rule. It is not in `ASKABLE`, so Ask cannot flip it.

Either off, every wallet route answers **404** (`service.gate`), a child always gets 404, and no wallet card or button is offered (the Rules page shows the switch as fixed-off when the deployment lacks it). The wallet appears nowhere in Ask, the brief or the digest, and reads and writes no wallet data.

## What it does

- **Link a wallet** to your account by signing a Sign-In with Ethereum message (EIP-4361, one fixed shape, domain and URI pinned to the passkey origins, ten-minute one-use nonce). One live link per address, five per person.
- **Sign in with a wallet** (same message, purpose `signin`). Every failure reads the same. It issues an ordinary session token but is **not** a passkey sign-in, so it does not open a household whose family key is split into shares.
- **The family wallet**: a guardian names its address and three limits (one transfer, a day, a month), in whole tokens. Changing the address voids every open proposal.
- **Transfers**: an adult or guardian proposes (payee, amount, memo). Limits are checked on proposal and again on approval. A payee never paid before is flagged `payee_new`. A **guardian approves by signing a fixed text** that names the transfer id, its fingerprint, amount, payee and the family wallet; the signer is recovered and must be a wallet linked to that guardian. A proposer cannot approve their own while another guardian exists. FamilyOS **never sends**: the guardian sends the call shown (`transfer(payee, amount)` to the token contract) from the family wallet and reports the hash; the chain is then read and the transfer is `settled` only if the token contract logged exactly that transfer, from the family wallet to that payee, for at least the approved amount. A network that does not answer changes nothing. Proposals and unsent approvals lapse after `wallet_approval_hours` (24).
- Read-only balances of the family wallet (native and the test token), cached 20 s.

## Leaving

- **Switch off** keeps the data. The routes are hidden, nothing reads it.
- **Delete** (`POST /v1/wallet/delete-data`, guardian, typed confirmation `delete wallet data`) erases links, nonces, the family wallet and every transfer, and records counts in the audit log. It works with the household switch off (that is when you would use it) but not when the deployment does not offer the module.
- **Erasing the household** removes the same rows by `ON DELETE CASCADE`.

## The module's contract (for the next optional module)

1. One package; the rest of the code touches it at **one call**, `wallet.register(app)` in `main.create_app`, which mounts its router and registers its audit wording (`audit.SAY_HOOKS["wallet"]`).
2. One household column (`households.wallet_enabled`) and one rules catalogue entry, so the switch shows whether or not the package is loaded. Its own tables hang off the household with `ON DELETE CASCADE`.
3. Every handler starts with a gate that answers 404 when either switch is off.
4. Audit rows are prefixed with the module name; ids, counts and hashes only in `detail`.
5. Off keeps data; a separate guardian action deletes it, typed and audited.
6. Tests: `tests/test_wallet.py`.

## Not done / not verified

- **The console card is built** (`familyos/web/wallet.js`, Settings, Privacy and security): it draws nothing unless `GET /v1/wallet` answers, link a wallet, name the family wallet and limits, propose, approve (the full text to be signed is shown first, then signed with the browser wallet's `personal_sign`), send from the family wallet (`eth_sendTransaction`, only if the connected account is the family wallet), check the network, delete. It was **not opened in a real browser or with a real wallet**: `tests/test_wallet_js.py` runs its script under node only.
- **No iPhone screen**, and **no "Sign in with a wallet" button** on the sign-in page yet (the API exists; the button would need the deployment to say publicly that the wallet is offered).
- **Never run against a real wallet or the live test network.** Signatures are made in tests with `eth-account`; the chain reads are tested with stand-in receipts. The USDC test-token address and RPC URL are the defaults in `settings.py` and were not checked against the network in this build.
- The sign-in rate limit reuses `rate_passkey_per_ip`; it is in-process like the others.
