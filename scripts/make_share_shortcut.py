"""Builds the generic "Share with FamilyOS" Shortcut (the person pastes their token at import) and signs it. See familyos/shortcut.py.

    .venv/bin/python scripts/make_share_shortcut.py --server https://home.example.ts.net

Needs a Mac (`shortcuts sign`). Written to .shortcuts/Share-with-FamilyOS.shortcut, which is where the console looks when it cannot sign one per
person itself (FAMILYOS_SHARE_SHORTCUT_FILE changes that). The file has the server's address and nothing secret.
"""
import argparse
import sys
from pathlib import Path

from familyos import shortcut


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True, help="the address the phone reaches FamilyOS at, https://...")
    ap.add_argument("--out", default=".shortcuts/Share-with-FamilyOS.shortcut")
    args = ap.parse_args()
    if not args.server.startswith("https://"):
        print("the server address must be https://", file=sys.stderr)
        return 2
    try:
        shortcut.sign_sync(shortcut.build(args.server), Path(args.out))
    except (RuntimeError, OSError) as exc:
        print(exc, file=sys.stderr)
        return 1
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
