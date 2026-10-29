# Reading WhatsApp from a member's own linked session (built 15 Oct 2026, not yet run against a real account)

**What it does.** A member links WhatsApp Web (a companion device on their own number) in a browser profile on this machine, names up
to eight chats, and accepts what it costs. Every 30 minutes the newest messages in those chats, and only those, are handed to the same
intake as a forwarded message (`gateway.receive_whatsapp`, marked second-hand, with the chat and author in the source). Dates and tasks
come up as proposals. It never sends, replies, reacts or opens a chat nobody named: the reader (`execution/whatsapp_reader.py`) has no
method that writes.

**Off by default.** `FAMILYOS_WHATSAPP_WATCH_ENABLED=true` (the user edits `.env`), then each member turns it on for themselves in the
console (Household → WhatsApp reading), Telegram (`/whatsapp`, which can also send the link code) or the API (`/v1/me/whatsapp`).

**The costs, shown before the yes** (`whatsapp_watch.CONSENT`): WhatsApp's [messaging guidelines](https://www.whatsapp.com/legal/messaging-guidelines?lang=en)
list unofficial clients and automation among the things not to do, so the number could be restricted; a linked session can read every
chat on the account; opening a chat marks it read for the other person; the logged-in browser profile is a credential on this machine
until forgotten; and the text goes to the model that reads this household's notices. A hosted model needs its own explicit yes
(`cloud_ok`); a household whose floor is above cloud cannot use it until its notice model is private.

**Why a browser profile, not a sealed session.** WhatsApp Web keeps its sign-in in browser storage the page cannot export, so it cannot be
sealed and restored like a cookie jar (`execution/sessions.py`). The profile directory (`~/.familyos/whatsapp/<member>`, mode 700)
is the only thing that holds the link. `Stop and forget` deletes it; remove the device in WhatsApp too.

**Linking.** `POST /me/whatsapp/link` opens the profile headless, chooses "Link with phone number", types the member's phone and returns the
8-character code; the member types it in WhatsApp → Linked devices. The page polls `GET /me/whatsapp/link`. A lapsed link (WhatsApp logs
companions out after a spell of phone inactivity) is said once through Telegram or email, and the sweep leaves it alone until relinked.

**Not verified.** The page selectors (`whatsapp_reader.py`, top) come from markup public scrapers rely on and have not been run
against a real account; they drift, and a mismatch reports an error rather than guessing. The unit tests use a fake reader. First real
run: link one throwaway chat, press Read now, and read the page's error if it fails.

**Whose chat it is.** A message from a named chat carries its name (`chat_name`), so the existing source-to-school rule applies: say once
that the chat belongs to a school (`PUT /v1/household/source-schools`, key `whatsapp:group:<chat name, lower case>`) and every notice from it is
attributed on arrival to the children at that school (`extraction/attribute.py`), as long as their household-records consent stands. Set
for the dev household on 15 Oct 2026: `whatsapp:group:26-27 fcit pp1 a` -> Bright Start (Lily's school). A per-chat "this is for…" choice in
the WhatsApp card is not built yet.
