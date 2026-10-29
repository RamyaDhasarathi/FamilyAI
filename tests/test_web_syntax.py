"""The console's script has to parse. Committing it hunk by hunk once left main with a file that did not (14 Oct 2026),
and nothing in the suite noticed because no test loads it."""
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "familyos"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("path", ["web/app.js", "web_classic/app.js", "web_cockpit/cockpit.js", "web_home/index.html", "web_kid/index.html"])
def test_the_scripts_parse(path):
    p = WEB / path
    if path.endswith(".html"):
        import re
        src = p.read_text()
        scripts = "\n".join(re.findall(r"<script>(.*?)</script>", src, re.S))
        tmp = Path(__import__("tempfile").mkdtemp()) / "inline.js"
        tmp.write_text(scripts)
        p = tmp
    r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[:600]
