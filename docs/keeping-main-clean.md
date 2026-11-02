# Keeping main clean

`main` is private today but is meant to be shareable at any moment. It must hold no real family, school, place or machine of the founder.

- **Fixtures, tests, previews, examples, comments:** made-up names only. Lily, Noah and Maya are the children and an adult; Alex is the founder's stand-in;
  Oakridge and Bright Start are the schools; Riverside Tower, Station Road and Northfield are places. `tests/test_no_personal_data.py` fails the run if a real name
  returns. Fix the new line, not the test.
- **Real values the system needs** live in configuration, never in git: `.env` (hosts, keys), `~/.familyos/` (the school-app mapping), `ios/Local.xcconfig` (bundle
  prefix and Apple team), and the database (a household's own settings).
- **The founder's own notes** that need real names go in `docs/private/` (gitignored). `docs/todo.md` stays tracked and uses roles ("the older child") for new entries.
- **Sharing code with someone outside** is done from a generated copy, never by inviting them to `main`: `scripts/make-share-copy.sh [dir]` exports the current commit,
  scrubs every rule in `scripts/share_scrub.py` (including bundle ids), leaves out `docs/todo.md`, and makes one fresh commit with no history and no remote. Check what it
  produced before sending it. The copy is safe to hand over only after the open security items in `docs/todo.md` are fixed or disclosed to the recipient.
- **History** still contains real names from before this rule; it holds no keys or tokens (checked 17 Oct 2026). Do not rewrite it casually: it breaks tags and clones.
