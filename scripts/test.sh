#!/bin/sh
# Run the suite against the test database, and only the test database.
#
# The suite drops its schema before it starts. On 2026-10-06 a shell that had
# sourced .env carried FAMILYOS_DATABASE_URL (the dev database) into pytest,
# and the household, the mailbox and 153 messages went with it. This script
# is the one way to run tests from now on: it forgets every FAMILYOS_*
# variable the shell may hold, pins the test database by name, and
# tests/conftest.py refuses anything whose name does not say "test" besides.
#
#   scripts/test.sh                 # the whole suite
#   scripts/test.sh tests/test_x.py -k something -x
#
# Override the test database with TEST_DATABASE_URL if yours lives elsewhere;
# its name must still contain "test".
set -eu
cd "$(dirname "$0")/.."
TEST_DB="${TEST_DATABASE_URL:-postgresql://localhost:5432/familyos_test}"
case "$TEST_DB" in
  *test*) ;;
  *) echo "refusing: TEST_DATABASE_URL must name a database with 'test' in it, not $TEST_DB" >&2; exit 2 ;;
esac
# TMPDIR rides along: tesseract and the sandboxed parser write scratch files there.
exec env -i HOME="$HOME" PATH="$PATH" LANG="${LANG:-en_US.UTF-8}" TMPDIR="${TMPDIR:-/tmp}" \
  TEST_DATABASE_URL="$TEST_DB" \
  .venv/bin/python -m pytest -q -p no:warnings "$@"
