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
# One run at a time: two suites on one test database drop and migrate the same schema and deadlock each other (seen
# 14 Oct 2026, when a review run and a work run overlapped). A second run waits for the first, or takes over from a
# run that died.
LOCK="${TMPDIR:-/tmp}/familyos-test.lock"
waited=0
until mkdir "$LOCK" 2>/dev/null; do
  holder=$(cat "$LOCK/pid" 2>/dev/null || true)
  if [ -n "$holder" ] && ! kill -0 "$holder" 2>/dev/null; then rm -rf "$LOCK"; continue; fi
  [ "$waited" -eq 0 ] && echo "another test run is using the test database; waiting for it" >&2
  waited=$((waited + 2)); [ "$waited" -gt 1800 ] && { echo "gave up waiting for the other test run" >&2; exit 3; }
  sleep 2
done
echo $$ > "$LOCK/pid"
trap 'rm -rf "$LOCK"' EXIT INT TERM
# TMPDIR rides along: tesseract and the sandboxed parser write scratch files there.
env -i HOME="$HOME" PATH="$PATH" LANG="${LANG:-en_US.UTF-8}" TMPDIR="${TMPDIR:-/tmp}" \
  TEST_DATABASE_URL="$TEST_DB" \
  .venv/bin/python -m pytest -q -p no:warnings "$@"
