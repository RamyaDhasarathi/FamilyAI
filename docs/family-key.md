# The family key (one recovery phrase, or Shamir sharing), steps 1 and 2 built 14 Oct 2026; one-tap mode 15 Oct 2026

## What the family is promised, exactly

"The household's key is held by your family. We cannot unwrap it. Your original files, your mailbox connection and your signed-in sessions
are unreadable to us at rest and in any backup, until an adult unlocks the household."

It is not "we can never see your data". While the household is unlocked the server decrypts what it must to read a notice, and the model
providers it calls see what is sent to them. The text read out of a notice is sealed under the same key for the quote behind each date and for
the title and names of each claim and obligation (step 2, "Sealed columns" below); other tables still hold copies of a title in the clear. Say only the
first paragraph, and say what is sealed only as far as that section says.

## Make it private: one tap (built 15 Oct 2026)

The shares ceremony (begin, write them down, paste them back) is still there, under "Advanced: split among several people". For an ordinary
family it was too much, so the Family key card, and the Family key screen on the phone, now lead with one button.

**What the person does.** Press **Make it private**. A recovery phrase is shown once; download or print it, tick "I have saved it", press Done.
That is all. Everyday opening is a passkey tap in the browser; the phone uses the phrase for now.

**What it does underneath.**
- The family secret S is one **recovery phrase**: a SLIP-39 share with threshold 1 (33 words, checksummed). The household key K is wrapped under a
  key derived from S, as before. The phrase is returned once and never stored or logged; the ledger records only that it was made.
- Each **trusted device** gets its own random 32-byte device secret D that wraps the same K (`family_key_devices`, migration 0087). The server keeps
  only the wrapped copy. D lives on the device: the console keeps it in this browser's localStorage, the phone keeps none (below).
- **Switch-on is two steps**, so a device that failed to keep its secret cannot lock a family out: `POST /household/family-key/simple` makes the phrase
  and the device secret and changes nothing; `POST /household/family-key/simple/done` takes the device secret back, checks it unwraps the very key in use,
  and only then drops the server's own copy. (The server cannot check that the phrase was saved; the page asks for the tick.)
- **Unlock on a device** (`POST /household/family-key/unlock-with-passkey`) needs both a passkey sign-in in the last `family_key_passkey_minutes`
  (default 15; the session token carries `passkey_at`, set only by a passkey sign-in) and that device's secret. A stolen token, or a copied database, alone opens
  nothing. A session that is not a recent passkey one is refused with `403 passkey_needed`, and the console then asks for a passkey and retries.
- **Recover** (`POST /household/family-key/recover`) opens the household with the phrase when no device is to hand. **Trust another device**
  (`POST /household/family-key/devices`) needs the household already open. **New phrase** (`POST /household/family-key/new-phrase`) re-wraps K under a
  fresh S; the old phrase stops working and devices keep working. **Go back** to the server key needs the phrase.

**The honest sentence for this mode.** "FamilyOS keeps no key it can open your household with on its own. It opens when one of your devices, with your passkey,
or your recovery phrase, says so." It is the same limits as before: while unlocked, the server and the model provider see what is read; a lost phrase *and* every
lost device means the household cannot be opened, by anyone.

**How it is weaker than the next step, said plainly.**
- The device secret is a stored secret, not a hardware-held one. Anything that can read this browser's localStorage (a script injected into the page, malware
  on the machine) can copy it, and with a passkey sign-in on that machine open the household. A WebAuthn PRF secret never leaves the authenticator.
- While a device is opening the household, the server sees that device's secret for the length of that request, and holds K in memory for the unlock window.
  An operator with a live shell on a running, unlocked server can read K; the attested-key-release step is what removes that.
- The phone is not yet a trusted device. Passkeys on iOS need an Associated Domains entitlement and the paid team, so the app unlocks with the phrase only.
  The switch-on made from the phone makes a device secret in memory, hands it back, and retires that device at once; it keeps no secret.

**The PRF path (designed, not built).** WebAuthn's PRF extension lets a passkey derive a secret inside the authenticator from a salt the server supplies:
D = PRF(salt) at `navigator.credentials.get` time, so no device secret is stored anywhere and the server never sees it. Plan: at passkey registration ask for
`extensions.prf.enabled`; at enable time derive D from the same passkey and wrap K under it; at unlock the PRF output replaces the stored secret. Caveats found
in the research, and the reason this is not the only path: PRF output can differ for the same passkey and salt between devices that share it through iCloud
Keychain, and over the QR cross-device flow (Apple developer forum thread 774112, partly fixed in Safari 18.2); support is Safari 18+ / iOS 18, Chrome 132+,
Android's Google Password Manager. So PRF would be tried first, the stored device secret kept as the fallback, and the phrase as the floor. Not verified on this
Mac or iPhone.

## How it works

- Every household has one 256-bit data key K. By default the server's master key wraps it (`households.wrapped_key`), so the operator can unwrap it.
- Opt in (a guardian): a random 256-bit family secret S is made and split into **n word shares, any t of which rebuild it** (SLIP-39,
  `shamir-mnemonic` 0.3.0, MIT, no dependencies; each share is 33 words with a checksum, so a typo is caught and shares from different
  sets refuse to combine). K is wrapped under a key derived from S (HKDF-SHA256, AES-GCM). The server keeps that wrapped copy and, once the
  opt-in is confirmed, **deletes its master-wrapped copy**. No share is ever stored.
- **Unlock**: any adult gives t shares; the server rebuilds S, unwraps K, drops S, and keeps K **in this process's memory** for
  `FAMILYOS_FAMILY_KEY_UNLOCK_HOURS` (8). **Lock** clears it; a restart clears it. Everything that needs K while locked fails with HTTP 423
  `household_locked`.
- **Two-step switch-on** so a family cannot lock itself out: `begin` shows the shares once and changes nothing; `confirm` needs t of them
  given back, requires that they unwrap the very key in use, and only then drops the server's copy.
- **Reshare** (someone leaves, a share is lost): new S, new shares, the same K; the old shares open nothing. No data is re-encrypted.
- **Disable**: back to the master key, needs the family's shares: the family decides, not the operator.
- Guessing is slowed (10 tries an hour per household) and audited; shares and secrets never reach the ledger.

## What it does not do yet

1. **Extracted text is sealed only in part.** Quotes, claim titles, subject names, issuers and obligation titles are sealed (below). Notes, job results and cached
   model answers, the other tables' titles, and every date and amount are not (docs/todo.md, "Encrypt the extracted text").
2. **One process.** The unlocked key lives in memory in one process. A deployment with several workers needs a shared, short-lived, memory-only
   cache or sticky routing before this is switched on for real households.
3. **Background work stops while locked.** Mail polling, sweeps and anything that needs K fail with 423 and wait. A locked household
   receives nothing readable. Later: seal incoming data to a household public key so it can be received while locked and read when unlocked.
4. **Shares are words on paper.** Next they are sealed to each member's passkey or phone, so a share lives in a device's secure hardware
   and an unlock is a tap on t devices, not typing 66 words. Passkeys also replace the emailed sign-in link.
5. **No governance for hard cases** (divorce, a death, a member who will not cooperate). Needs a written rule for who holds shares, a
   trusted-person share, and what a court order does.
6. **Memory is not magic.** Anyone with a memory dump of the live server while unlocked has K. The model for the next stage is that the key
   never reaches the server at all: processing on the family's own devices, with end-to-end encrypted storage.

## Sealed columns (audit of 23 Oct 2026)

Done by reading every write and every SQL use of each column in `familyos/`. A value is `enc:v1:<household>:<column>:<ciphertext>`; the column name is part of what is
signed, so a value cannot be moved to another column and opened. Reads through `db.pool()` open it (a value on its own, or inside an array a query built), a locked
family-held household answers 423, and `settings.seal_extracted_text` off stops sealing new text without breaking what is sealed or what is not yet.

| Column | Written at | SQL that needed the plaintext, and what was done |
|---|---|---|
| `claims.quote` ("quote") | `extraction/service.py` (claims insert), `standing.py` (`_make`); `documents.py` masks numbers in unsealed rows only | none (sealed since 14 Oct) |
| `claims.title` ("claims.title") | the same two sites | `warranty_hints.waiting`: a claim whose title says warranty, return, exchange or replacement (was `c.title ~* ...` in SQL) now matches in Python after the rows are opened, still the first 20 notices. No ORDER BY, GROUP BY, DISTINCT or unique index touches it. |
| `claims.subject_name` ("claims.subject_name") | `extraction/service.py` (only a consented child's name is stored), `standing.py` stores NULL; `erasure.py` sets NULL | none: erasure and `export.py` already compared names in Python (`consent.names_match`); `DISTINCT artifact_id, subject_name` in export only de-duplicates and its result is matched in Python |
| `claims.issuer` ("claims.issuer") | `extraction/service.py` | none: only written; the copy in `documents.issuer` is still plain |
| `obligations.title` ("obligations.title") | `extraction/service.py` (`rows` stays plain for `_standing_rules`; only the stored copy is sealed), `standing.py` | `scenarios.school_reopens` (two title regexes) and `routines._events` (`trip_soon`) now match in Python; `warranty_hints` as above; `ORDER BY ... o.title` tie-breaks in `schoolday.py` (day and forms) and `kid.py` (a child's day) are now made in Python; `inbox.py` previews use `array_agg(o.title)`, which the pool opens element by element |
| `extractions.notes` | `extraction/service.py` | **not sealed**: it holds machine tags (`no_text`, `ocr_unavailable`, `from the picture`), no family words, and `medications.py` searches it in SQL. Sealing a JSONB list of tags for no privacy gain was not worth the risk. |

What stays readable even so: a to-do, document, medication, warranty or calendar entry made from a notice keeps its own plain copy of the title; the audit log, job
results, notification and reminder text, Ask's and the model's prompts (the server reads a notice while it is unlocked), search embeddings (in memory), and the
dates, amounts, statuses and ids of every row. Do not describe these as sealed.

The tests that guard it are `tests/test_sealing.py` and `tests/test_sealing_columns.py` (every sealed column is ciphertext in the raw pool and plain through the application's pool;
a locked household answers 423; the moved searches give the same answers; export and a consent withdrawal work on sealed names). The test suite reads through the application's pool
(`tests/conftest.py`); a test that needs the bytes as stored uses `db.raw_pool()`, and a test must not search or sort a sealed column in SQL.

## Not web3 login

Wallets and seed phrases are the wrong thing for a family: one lost phrase locks everyone out. Sign-in stays an emailed link now and passkeys
next; Shamir shares are the social-recovery layer (the same pattern as key-unsealing in Vault, and social-recovery wallets), not a login.

## Order

Step 1 (this): the split, the two-step switch, lock and unlock, reshare, disable, and the Household page card.
Step 2 (built): seal the extracted text under K (`sealing.py`; the shared pool opens sealed values on read, so a query that only selects them did not change). `claims.quote` first (14 Oct), then, on 23 Oct 2026, `claims.title`, `claims.subject_name`, `claims.issuer` and `obligations.title`; `seal_extracted_text` is **on by default** since 23 Oct 2026; a sweep backfills old rows and skips a household whose key is locked. Still in the clear: dates, amounts, kinds, statuses and ids, the other text columns of `claims` (place, applies_to, change, amends, date_text, time_text, dose_text), `extractions.notes` (machine tags only), and every other table, including the copies of a title made into to-dos, documents, medications, warranties and calendar entries. See "Sealed columns" below.
Step 3: shares sealed to passkeys; unlock by tapping t devices.
Step 4: receive while locked (household public key).
Step 5 (later): end-to-end models: the family's device holds the key, the server stores ciphertext only.

## Research notes (14 Oct 2026)

### Web3Auth / MetaMask Embedded Wallets: borrow the pattern, do not depend on it
Checked against its docs (docs.metamask.io/embedded-wallets, which web3auth.io/docs now redirects to), its pricing page and blog; two items came only from search results (the CertiK audit headline, an academic paper on web3 auth flaws).
- Key custody is a 2-of-3 threshold: a share the network releases after login (OAuth, email, custom JWT), a share on the user's device, and a user-held recovery factor. Recovery on a new device needs any two. In its TSS mode the app never sees the key; in its Shamir-style SDKs the app can read it (the iOS SDK has `getPrivateKey()`).
- The network runs distributed key generation (new keys need more than three quarters of nodes honest, retrieving needs more than half). The node count and current operators are not stated in the docs I read, and I found no documented shutdown or export path. So a hosted network as the only root of trust adds a vendor and an operator set to the trust story, against the aim that the family holds the key.
- It gives a wallet key, not a household key. Shares belong to individuals, so a household key still needs our own wrapping per member. Its Node SDK logs in with a JWT from your own server, which would put the key back on the operator's side. Passkeys are a paid tier; self-hosting was not found; pricing is per monthly active wallet.
- Verdict: the pattern (device factor + identity-gated factor + user-held recovery) is the right shape and is what steps 3 and 5 below build, using passkeys and the family's own shares. If it is ever used, as one wrapping factor beside a family-held recovery secret, never the sole custodian.

### Confidential and private inference (what can honestly be promised)
From vendor docs and security write-ups; several items only from search snippets and marked as such in the research.
- **TEEs** (NVIDIA Hopper/Blackwell GPU confidential computing with Intel TDX or AMD SEV-SNP) protect against the operator's software and staff, not a determined operator with physical access: the TEE.Fail result (a sub-$1,000 DDR5 interposer extracting attestation keys; Intel and AMD call physical attacks out of scope) shows it. Attestation proves which measured code booted, not that it is bug-free, and Privatemode says it is checked when trust is established, not on every request. Anthropic's own paper relies on providers for physical and hypervisor security and is a research sketch, not a product.
- **Apple Private Cloud Compute** is the reference design (stateless, no privileged access, non-targetable, verifiable transparency log). No third party can run workloads on it today; reports of wider developer access in iOS 27 are unconfirmed on Apple's own pages.
- **Hosted confidential inference** exists and is young: Privatemode (Edgeless; reproducible builds, OpenAI- and Anthropic-compatible, open-weight models, EU), Tinfoil, NEAR AI Cloud, Phala, Venice. No independent audit was found for any. There is no confidential Claude or OpenAI API, so those calls cannot be operator-blind. Latency and cost are unverified: benchmark.
- **On device**: Apple's on-device model is about 3B parameters with a small context; no benchmark was found for extracting dates and amounts from noisy notices, so test on our own corpus.
- **FHE and MPC** for LLM inference: hours per forward pass; not usable.

### The ladder, cheapest to strongest, and the sentence we may say at each rung
1. Hosted Anthropic or OpenAI with zero-retention terms: "we minimise and delete; the provider could technically see it."
2. Redaction before the call plus on-device OCR: "identifiers are stripped before anything leaves your device" (not verifiable by the family).
3. A confidential-inference provider behind an OpenAI-compatible adapter, attestation pinned in the family's app: "neither we nor the provider can read it, unless someone has physical access to the datacentre; you can check the attestation."
4. Our own confidential VM (Azure confidential GPU VMs, Phala dedicated): the same claim with fewer parties, plus operations work.
5. On device or a home server, for the most sensitive documents (IDs, prescriptions): "never leaves your hardware", at lower model quality.

The family key (this document) governs what is stored; the ladder governs what is processed. The honest order is: family key, seal the extracted text, an OpenAI-compatible adapter so rung 3 can be tried on synthetic documents, then rung 5 for the most sensitive kinds.

## TEE hosting and end-to-end storage: how they plug in (design, not deployed)

The family has its own TEE and end-to-end hosting; it is not yet in front of FamilyOS, so nothing below is claimed to users today.

**TEE hosting.** The server (and the household's own model) runs in a confidential VM on hardware we control (Intel TDX or AMD SEV-SNP, with GPU confidential computing for inference). The build is reproducible and its measurement is published.
- **Attested key release.** The enclave generates a key pair at boot and binds its public half into the attestation report. The family's app checks the report against the published measurement before it sends anything. Shares are encrypted to that key, so the family secret is rebuilt, and the household key unwrapped, only inside the enclave. The unlocked key never exists outside it. Today's version holds it in the app process's memory; this removes the memory-dump and operator-shell cases.
- **Outside the enclave** are the database and the object store, holding ciphertext only. That needs the extracted text sealed in full (titles and names, not only quotes) and the SQL searches over them moved into the application.
- **Where to run it (read 20 Oct 2026, Google's Confidential VM overview).** Google Cloud sells exactly the pieces above as VMs: AMD SEV (boot attestation through its vTPM), AMD SEV-SNP (attestation reports on request from the AMD Secure Processor; protects against replay and remapping by the hypervisor), Intel TDX (a trust domain, designed to resist some physical memory attacks), and NVIDIA confidential computing on attached GPUs for the household's own model. Confidential GKE nodes and Confidential Space build on it. The page does not say which regions or machine types carry each, what it costs, or what it does not protect against; whether India or the UAE has any is the first thing to check, since the household's data may need to stay in country. Azure confidential GPU VMs are the other named option above.
- **Until then, with more than one process (`FAMILYOS_MULTI_WORKER=true`, docs/deploy.md).** The unlocked key is also kept in `family_key_unlocks`, wrapped under the server's master key, until the unlock expires or someone locks. This is the one place the unlocked state touches the database, so: a database backup taken inside the unlock window plus the master key opens that household (the master key is not in the database, and an operator with a live shell on an unlocked server could already read the key from memory). Off by default; with one process nothing is written and a restart still locks every private household. A lock, a disable and an erasure delete the row; failed unlock tries are counted in `family_key_attempts`, not in memory, so a guess cannot be spread across processes.
- **Re-attest** on every unlock; lock automatically if the measurement changes; keep a public log of measurements.
- **What it does not stop:** a determined attacker with physical access to the machines (the TEE.Fail class of attack on the memory bus), so the datacentre needs real physical controls and independent monitoring. The claim is "we cannot read it unless someone has physical access to the hardware, and you can check which code runs", not "impossible".

**End-to-end storage.** The key is derived on and held by the family's own devices (phones, passkeys), documents are encrypted on the device before they leave it, and the server stores ciphertext only.
- Reading a notice then happens either **on the device** (OCR and a small on-device model, for the most sensitive kinds: IDs, prescriptions) or **inside the TEE**, to which the device releases a per-session key after verifying attestation.
- Search and the graph that need plaintext run on the device or inside the enclave, never on the plain server.
- The Shamir shares become the recovery layer for the device-held key, with the governance rules in "What it does not do yet" above.

**The order.** (1) Seal titles and names. (2) An OpenAI-compatible model adapter, so the TEE-hosted model can be swapped in without touching extraction. (3) Attested key release and passkey unlock. (4) Receive while locked (a household public key). (5) End-to-end storage with on-device processing for the most sensitive kinds.

**What we may say at each stage**
- Today (family key on): "Your family holds the key. We cannot unwrap it. Your files, mailbox connection and sessions are unreadable to us at rest and in backups."
- With TEE hosting: "...and the key opens only inside a server whose code you can verify; we and the cloud cannot read it, short of physical access to the hardware."
- With end-to-end storage: "...and your devices hold the key; the server stores ciphertext only."

## Target architecture, from design review (14 Oct 2026)

Two outside reviews of this design agreed with its direction and sharpened it. They replace the "unlocked key in server memory" model of step 1, which stays only as a stopgap. Nothing in this section is built yet unless it says so.

**Layers, each solving a different problem**
| Layer | Approach | What it provides |
|---|---|---|
| Login | An individual passkey per member | Face ID or device unlock, no emailed link |
| Data protection | Encrypt on the device before upload | The server stores ciphertext only |
| Access | Separate personal and shared-vault keys | Each person gets only the spaces they are entitled to |
| Recovery | Shamir shares of a recovery key (built: SLIP-39 split, confirm, reshare) | Recover access through a family quorum; the company holds no share |
| Processing | An attested TEE is the endpoint where decryption and inference happen | Plaintext exists only inside a verified environment, never on the plain server |
| Agents | Explicit, limited, expiring grants | An agent receives the items a task needs, not the vault |

**Principles**
1. **E2EE and TEE are different things.** End-to-end encryption protects the path between endpoints; a TEE protects processing. A model cannot reason over ciphertext, so the attested TEE is the endpoint where decryption and inference happen. The device verifies the attestation (including the approved software identity) and sends only the task data over a channel bound to that attested environment; the answer comes back encrypted to the authorised device.
2. **Keep the family's key outside the TEE.** Send selected data or narrowly scoped keys. FamilyOS already has the hierarchy for it: household key, then a per-member scope key for private notices, then a key per file. A grant to the TEE is a set of those keys with a purpose, an expiry and an audit entry, approved by the family and revocable. That limits what a compromised inference environment could expose.
3. **Recovery is not daily use.** Passkeys open the app each day; the Shamir shares are used only to recover access (a lost device, a family dispute settled), on a trusted device, never per login or per AI request. Keep the **recovery key separate from everyday encryption keys**. Shamir brings the whole secret together briefly when reconstructed; it is not threshold computation that keeps a secret distributed throughout an operation.
4. **No single master key.** A family has internal privacy boundaries: the shared vault (calendar, groceries, household documents) for selected members; an adult's private space for that adult; children's spaces by explicit guardian permission; financial credentials and agent permissions in a separate restricted space. Recovering the shared vault must not reveal an adult's private one, and the family is told plainly that a recovery quorum can recover whatever that recovery key protects.
5. **The whole plaintext path must be protected.** If the TEE forwards prompts to an ordinary external model API, that provider sees them. Inference, retrieval, CPU and GPU memory, temporary files, OCR and logging all belong inside the protected design or on the device. External tools (email, shopping, bill payments) still receive what they need to act, and the family is told which.
6. **Background agents run on grants.** While family devices are offline, the family approves a limited, expiring grant to an attested workload: reminders and heads-ups work without a permanently running agent holding the vault. Start with grants of hours or days, listed on the family page with a revoke button.
7. **Metadata is a decision.** Reminders, heads-ups and the money timeline need dates, amounts, kinds and ids readable by the server. Say so plainly at first, or move scheduling inside the TEE later.
8. **Avoid putting family membership or activity on a public chain.** A wallet connection may be offered for payments, but it is not part of recovery or sign-in.

**Hard cases to decide before this is promised to anyone:** lost-device revocation; recovery after a family separation or a death (who holds shares, what a court order does); key rotation, remembering that removing someone cannot erase what they already decrypted or copied.

**Open question to verify, not assumed:** whether a passkey can also derive or wrap key material on both iPhone and Android (the WebAuthn PRF extension or an alternative). If it cannot, each device keeps its own key pair in secure hardware and wraps the vault key to it.

**The promise this architecture can honestly support** (only once the parts exist): "Family-owned keys. Encrypted storage. Confidential AI processing." And: "Your shared family vault is encrypted before upload. We cannot independently decrypt it or recover its key. You choose what is shared with AI." Never "nobody can ever read your data": TEE security still depends on hardware, attestation, approved code and the update process.

**Revised order:** (1) seal titles and names; (2) an OpenAI-compatible model adapter so a TEE-hosted or on-device model can be swapped in; (3) per-member passkeys and device-held keys, with separate personal and shared spaces; (4) per-file scoped keys and expiring grants for background work; (5) attested key release; (6) end-to-end storage with on-device processing for the most sensitive kinds. Step 1 as built (unlock by shares into server memory) is retired once (3) to (5) land.

### Web3Auth social-login flow, traced (14 Oct 2026, docs.metamask.io, several pages 404 or partial)
- A login in the Web SDK is `connect()`; on iOS the bundle id and a `{bundleId}://auth` redirect are allowlisted. The OAuth provider is configured as an "auth connection" (formerly verifier) in a dashboard; the user id from the provider is the verifier id. Different client ids, and different verifiers, give different keys.
- Each network node verifies the login token individually. Release is commit-reveal: once a threshold of nodes acknowledges a commitment the client reveals the token and each node returns its share encrypted to a temporary key. New keys need more than three quarters of nodes honest, rebuilding an existing key more than half. The key is 2-of-3: a network share, a device share (browser storage on the web; Keychain or encrypted preferences on mobile) and a user backup factor; the iOS SDK lists device, backup, social backup and password factors.
- A dapp server can verify a login from an ES256 token (JWKS published), checking issuer and audience because projects share the signing infrastructure.
- **Not verified:** whether a valid Google token alone pulls the network share; what happens on a new device or cleared storage (the MFA page was missing); the default session length (7 days in a snippet, up to 30 on a fetched page); how the key is returned in each SDK mode; the India and on-screen UX; behaviour under a compromised or phished Google account (the docs do not address it; if the second factor is optional, the Google account may be enough).
- **Verdict:** a poor root for a family data key (the key would still derive from a Google login with the vendor's network as a party), and adding it as the sign-in layer brings a third-party dependency into the trust model with no custody benefit. Borrow the experience, not the dependency: one-tap social sign-in, a device-held factor protected by biometrics, a backup factor the user controls, and quorum recovery.
