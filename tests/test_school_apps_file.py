"""Which school uses which phone app is local configuration (a JSON file), not code: built-ins are generic, the file extends or adds, and a bad file never breaks anything."""
import json
import os

from familyos.execution import apps
from familyos.settings import settings


def _touch(path, seconds):
    os.utime(path, (1, path.stat().st_mtime + seconds))        # the file's modification time is what decides a re-read


def test_without_a_file_the_built_in_apps_match_no_school():
    assert sorted(apps.APPS) == ["iossettings", "myclassboard"]
    assert apps.app_for_school("Oakridge Global School") is None and apps.APPS["myclassboard"]["bundle"] == "com.myclassboard.commonParentPortal"


def test_the_file_extends_a_built_in_app_and_adds_one_and_is_reread_when_it_changes(school_apps):
    assert apps.app_for_school("Oakridge Global School") == "myclassboard" and apps.APPS["myclassboard"]["bundle"] == "com.example.oakridgeApp"
    assert apps.app_for_school("Bright Start Preschool") == "brightstart" and apps.APPS["brightstart"]["notices"][0] == "Today's Highlights"
    assert "brightstart" in list(apps.APPS) and apps.get("brightstart")["service"] == "brightstart"
    school_apps.write_text(json.dumps({"myclassboard": {"schools": ["Hillside"]}}))
    _touch(school_apps, 5)                                       # a changed file is read again, without a restart
    assert apps.app_for_school("Hillside Primary") == "myclassboard" and apps.app_for_school("Oakridge Global School") is None
    assert "brightstart" not in list(apps.APPS) and apps.APPS["myclassboard"]["bundle"] == "com.myclassboard.commonParentPortal"


def test_a_bad_file_or_a_bad_entry_is_skipped_not_fatal(tmp_path, monkeypatch):
    bad = tmp_path / "bad.json"
    monkeypatch.setattr(settings, "school_apps_file", str(bad))
    bad.write_text("{not json")
    assert sorted(apps.APPS) == ["iossettings", "myclassboard"]
    bad.write_text(json.dumps(["a list"]))
    _touch(bad, 5)
    assert sorted(apps.APPS) == ["iossettings", "myclassboard"]
    bad.write_text(json.dumps({"newapp": {"label": "No bundle"}, "other": "text", "myclassboard": {"schools": ["x school"]}}))
    _touch(bad, 10)
    assert sorted(apps.APPS) == ["iossettings", "myclassboard"] and apps.app_for_school("X School") == "myclassboard"
