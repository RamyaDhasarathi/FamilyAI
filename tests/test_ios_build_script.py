"""ios/build.sh must say whether the build worked: it filters xcodebuild's output, and the filter must not decide the exit status."""
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "ios" / "build.sh"


def _run(tmp_path, xcodebuild_exit, xcodebuild_says):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("xcodegen", "exit 0"), ("xcodebuild", f"echo '{xcodebuild_says}'\nexit {xcodebuild_exit}")):
        tool = bin_dir / name
        tool.write_text("#!/bin/sh\n" + body + "\n")
        tool.chmod(0o755)
    return subprocess.run(["sh", str(SCRIPT)], capture_output=True, text=True, env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}, timeout=60)


def test_a_failed_build_fails_the_script_and_still_shows_the_errors(tmp_path):
    out = _run(tmp_path, 65, "Foo.swift:3:1: error: cannot find x in scope")
    assert out.returncode == 65 and "error: cannot find x in scope" in out.stdout


def test_a_build_that_works_passes(tmp_path):
    out = _run(tmp_path, 0, "** BUILD SUCCEEDED **")
    assert out.returncode == 0 and "BUILD SUCCEEDED" in out.stdout


def test_a_build_that_prints_nothing_the_filter_knows_still_reports_its_own_status(tmp_path):
    assert _run(tmp_path, 70, "something unexpected").returncode == 70
