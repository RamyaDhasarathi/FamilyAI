"""An installed copy of FamilyOS (the wheel, the Docker image) must carry every file the server serves, not only the first consoles."""
import glob
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "familyos"


def _declared() -> set[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]["package-data"]["familyos"]
    return {p for pattern in data for p in glob.glob(pattern, root_dir=PACKAGE)}


def _served() -> set[str]:
    """Each console is a directory under familyos/ named web*; the payment page serves only its built public/ folder. Sources and dependencies are not served."""
    out = set()
    for site in PACKAGE.glob("web*"):
        base = site / "public" if site.name == "web_pay" else site
        out |= {str(p.relative_to(PACKAGE)) for p in base.rglob("*") if p.is_file() and "node_modules" not in p.parts and p.name != ".DS_Store"}
    return out


def test_the_package_data_carries_every_file_the_server_serves_and_the_migrations():
    declared = _declared()
    missing = sorted(_served() - declared)
    assert not missing, f"not in package-data, so absent from a wheel: {missing}"
    assert any(p.startswith("migrations/") and p.endswith(".sql") for p in declared)
    assert len([p for p in declared if p.startswith("migrations/")]) == len(list((PACKAGE / "migrations").glob("*.sql")))
