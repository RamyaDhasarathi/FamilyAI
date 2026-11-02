#!/bin/sh
# Judge Ask with a real model on an invented household, in the test database only.
#
# Like scripts/test.sh this forgets the shell's FAMILYOS_* variables and pins the test database. It then lets
# through only the model settings from .env (never printed), because the model is the thing being judged.
#
#   scripts/ask_eval.sh            # all cases
#   scripts/ask_eval.sh -k bill    # one
set -eu
cd "$(dirname "$0")/.."
TEST_DB="${TEST_DATABASE_URL:-postgresql://localhost:5432/familyos_test}"
case "$TEST_DB" in *test*) ;; *) echo "refusing: TEST_DATABASE_URL must name a database with 'test' in it" >&2; exit 2 ;; esac
MODEL_ENV=""
for key in FAMILYOS_LOCAL_MODEL FAMILYOS_LOCAL_MODEL_URL FAMILYOS_LOCAL_MODEL_KEY FAMILYOS_EXTRACTOR FAMILYOS_EXTRACTION_MODEL FAMILYOS_EXTRACTION_EFFORT OPENAI_API_KEY ANTHROPIC_API_KEY; do
  line=$(grep -E "^${key}=" .env 2>/dev/null | head -1 || true)
  [ -n "$line" ] && MODEL_ENV="$MODEL_ENV $key=${line#*=}"
done
# shellcheck disable=SC2086
exec env -i HOME="$HOME" PATH="$PATH" LANG="${LANG:-en_US.UTF-8}" TMPDIR="${TMPDIR:-/tmp}" \
  TEST_DATABASE_URL="$TEST_DB" FAMILYOS_ASK_EVAL=1 FAMILYOS_EMBED_MODEL="" $MODEL_ENV \
  .venv/bin/python -m pytest -q -p no:warnings tests/test_ask_eval.py "$@"
