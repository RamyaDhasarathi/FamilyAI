"""What the image build is sent: the files the Dockerfile copies, and nothing that holds a secret or only weighs it down."""
import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _patterns() -> list[str]:
    return [line.strip() for line in (ROOT / ".dockerignore").read_text().splitlines() if line.strip() and not line.startswith("#")]


def _ignored(path: str) -> bool:
    parts = path.split("/")
    for pattern in _patterns():
        pat = pattern.rstrip("/")
        if pat.startswith("**/"):
            if any(fnmatch.fnmatch(part, pat[3:]) for part in parts):
                return True
        elif fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(parts[0], pat):
            return True
    return False


def test_the_build_context_leaves_out_secrets_and_the_heavy_folders():
    for path in (".env", ".env.local", ".env.production", ".git", ".venv", ".blobs", ".keys/payments_jwt.pem", "familyos/web_pay/node_modules/x/index.js", "ios/FamilyOS.xcodeproj"):
        assert _ignored(path), path


def test_the_build_context_keeps_what_the_dockerfile_copies():
    copies = [src for line in (ROOT / "Dockerfile").read_text().splitlines() if line.startswith("COPY ") for src in line.split()[1:-1]]
    wanted = ["pyproject.toml", "requirements.lock", "familyos/main.py", "familyos/web_welcome/index.html", "familyos/migrations/0001_foundation.sql"]
    assert {"pyproject.toml", "requirements.lock", "familyos"} <= set(copies)
    for path in wanted:
        assert not _ignored(path), path
