"""The web app's built scripts have to parse. Committing a script hunk by hunk once left main with a file that did not
(14 Oct 2026), and nothing in the suite noticed because no test loads it. The founder's console scripts this covered
were replaced by web/ on 29 Oct 2026; its sources are also checked by `npm run build` (tsc) in web/."""
import shutil
import subprocess
from pathlib import Path

import pytest

DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
SCRIPTS = sorted(p.name for p in (DIST / "assets").glob("*.js")) if (DIST / "assets").is_dir() else []


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.skipif(not SCRIPTS, reason="web/dist is not built in this checkout")
@pytest.mark.parametrize("name", SCRIPTS or ["none"])
def test_the_scripts_parse(name):
    r = subprocess.run(["node", "--check", str(DIST / "assets" / name)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[:600]
