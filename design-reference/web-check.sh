#!/bin/sh
# Re-runnable web baseline check (AGENT.md §3.4 / §13.1).
# The web UIs (familyos/web, web_classic, web_guide, web_orbit) are static files
# served by FastAPI with no build step, so "the web build" is: lint the Python,
# syntax-check every web JS file, and hash every file outside mobile/ and
# design-reference/. Run from the repo root:
#   RUFF=/path/to/ruff sh design-reference/web-check.sh
set -u
cd "$(dirname "$0")/.."
RUFF="${RUFF:-ruff}"

echo "## 1. ruff check ."
"$RUFF" check . --output-format concise 2>&1 | grep -E '^[^ ].*:[0-9]+:[0-9]+:' | sort
echo "summary: $("$RUFF" check . 2>&1 | grep -E '^Found [0-9]+ error')"

echo
echo "## 2. node --check on every web JS file"
find familyos/web familyos/web_classic familyos/web_guide familyos/web_orbit -name '*.js' | sort | while read -r f; do
  if node --check "$f" >/dev/null 2>&1; then echo "ok   $f"; else echo "FAIL $f"; fi
done

echo
echo "## 3. sha256 of every tracked file outside mobile/ and design-reference/"
git ls-files | grep -vE '^(mobile|design-reference)/' | tr '\n' '\0' | xargs -0 shasum -a 256 | shasum -a 256 | cut -c1-64
echo "files: $(git ls-files | grep -vE '^(mobile|design-reference)/' | wc -l | tr -d ' ')"
