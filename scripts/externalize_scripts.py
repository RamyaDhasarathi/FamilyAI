"""Moves every inline <script> in a console's index.html into a file next to it (boot.js, boot2.js, ...), so the
server can send `script-src 'self'` for that console. Order and position are kept: each block becomes a plain
<script src> at the same place, which runs at the same moment an inline block did.

    python3 scripts/externalize_scripts.py familyos/web/index.html [more.html ...]

Safe to run again: it only touches inline blocks. A new inline script added later is caught by
tests/test_script_policy.py.
"""
import re
import sys
from pathlib import Path

INLINE = re.compile(r"<script>(.*?)</script>", re.S)


def externalize(html_path: Path) -> int:
    text = html_path.read_text()
    n = 0

    def swap(m: re.Match) -> str:
        nonlocal n
        n += 1
        name = "boot.js" if n == 1 else f"boot{n}.js"
        (html_path.parent / name).write_text(m.group(1).strip("\n") + "\n")
        return f'<script src="{name}"></script>'

    out = INLINE.sub(swap, text)
    if n:
        html_path.write_text(out)
    return n


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(arg, externalize(Path(arg)), "inline script(s) moved")
