# Moving the dev household into private mode (plan, 14 Oct 2026)

The real dev household (`familyos_dev`: 4 members, 494 stored files, 3,521 extracted quotes still in the clear, one live
signed-in session, 32 MB) has its key held by the server. This plan moves it to a family-held key without losing or exposing anything.
Nothing here has been run. Each step names how to check it and how to undo it.

## What actually changes

The household's **data key does not change**. Blobs, sealed sessions and sealed quotes stay encrypted under it. Only the **wrapper** around
the key changes: from "wrapped by the server's master key" to "wrapped by the family's secret". So there is no bulk re-encryption and no
data rewrite except one thing: the 3,521 quotes that were stored before `FAMILYOS_SEAL_EXTRACTED_TEXT` existed are sealed by the backfill.

**The catch that decides the order:** any backup taken *before* the switch holds the key wrapped under the master key. Master key plus an old
backup opens everything, for ever. So a pre-switch backup is a safety net now and a leak later. It is kept only until the switch is
verified, then deleted. If old copies of the database may exist elsewhere, the data key has to be rotated (re-encrypt 494 blobs, re-seal
the quotes under a new key, re-wrap): not built, listed under "after".

## Preconditions

1. The simple "Make it private" flow (passkey + recovery phrase) is merged and the family-key test on the scratch household has passed.
2. The Mac stays awake for the window; no errand, sign-in sitting or harvest is open (`GET /v1/sign-ins/open`, jobs queue idle).
3. the founder is at the desk with the iPhone, and says go. Nothing below is done on a guess.

## Steps

1. **Back up, outside the repo.** `pg_dump -Fc familyos_dev > ~/Backups/familyos_dev-<date>.dump`; copy `.blobs/` beside it. The
   master key already lives in `.env` (never printed or moved by us). *Check:* restore the dump into `familyos_restore_check` and count rows
   (494 artifacts, 4 members). *Undo:* none needed; this changes nothing.
2. **Rehearse on the copy.** Run a scratch server (port 8091, never 8088) against `familyos_restore_check`, make it private there, restart,
   confirm it comes back locked and unlocks with the passkey and with the phrase. Fix anything before touching the real one.
3. **Seal the old quotes.** the founder adds `FAMILYOS_SEAL_EXTRACTED_TEXT=true` to `.env` (we do not edit it) and restarts the server. Run the
   backfill once by hand (`sealing.backfill(limit=5000)`; the scheduled sweep does 500 per 10 minutes). *Check:* `select count(*) from claims
   where quote not like 'enc:v1:%'` is 0 and the Needs-you page still shows the same quotes. *Undo:* set the flag off; sealed rows still open
   because the server still holds the key.
4. **Make it private.** In the console or the app, Make it private; save the recovery phrase to Files and a second place; tick "saved".
   *Check:* `key_mode = family`, the server's wrapped copy is gone (peek script), phrase saved twice.
5. **Restart and prove it.** Restart the server: the household must come back **locked**, then unlock by passkey, then lock and unlock by the
   phrase. *Check:* Needs you and the original file return 423 while locked and open after unlock.
6. **Live with it for a day.** While locked, nothing background can read the household: mail polling, nudges, Telegram intake and routines
   wait or report "locked", and resume on unlock. Expect to unlock after every server restart (the key is only in memory). That is the
   cost of the promise, and the dev server restarts often: if it is too much, keep dev on the server key and prove the flow on the scratch
   household instead.
7. **Delete the pre-switch backup** once steps 4 to 6 hold and the post-switch state is itself backed up. Keep one backup *taken after* the
   switch (it holds only the family-wrapped key).

## Rollback, by how far you got

- Before step 4: nothing changed; drop the scratch copies.
- After step 4: **Disable** on the Family key card (needs the phrase) puts the key back under the server. Data is untouched.
- If the phrase is lost and every passkey is gone: the household is unreadable by design. This is the one unrecoverable case, which is why
  step 4 requires two saved copies, and why the pre-switch backup is kept until step 7.
- Corruption of any kind: restore the step-1 dump (same blobs, same master key).

## After

Key rotation tool (cuts off old backups); sealing titles and names; receive-while-locked (a household public key) so mail and Telegram are
not lost while the key is closed. Production uses the same sequence with a real maintenance window and the rotation done first.
