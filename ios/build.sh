#!/bin/sh
# Generate the Xcode project from project.yml and build both targets for the
# simulator, ad-hoc signed with their entitlements (the Keychain refuses an
# app with no identity at all, even in the simulator). No team is needed.
set -eu
cd "$(dirname "$0")"
xcodegen generate --quiet
# The output is filtered for reading, but the exit status is xcodebuild's own: a failed build must fail this script.
log=$(mktemp)
status=0
xcodebuild -project FamilyOS.xcodeproj -scheme FamilyOS -sdk iphonesimulator \
  -destination 'generic/platform=iOS Simulator' -derivedDataPath build \
  CODE_SIGN_STYLE=Manual CODE_SIGN_IDENTITY=- DEVELOPMENT_TEAM="" PROVISIONING_PROFILE_SPECIFIER="" \
  build "$@" > "$log" 2>&1 || status=$?
grep -E "error:|warning: .*\.swift|BUILD (SUCCEEDED|FAILED)" "$log" || true
rm -f "$log"
exit "$status"
