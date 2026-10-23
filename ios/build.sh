#!/bin/sh
# Generate the Xcode project from project.yml and build both targets for the
# simulator, ad-hoc signed with their entitlements (the Keychain refuses an
# app with no identity at all, even in the simulator). No team is needed.
set -eu
cd "$(dirname "$0")"
xcodegen generate --quiet
xcodebuild -project FamilyOS.xcodeproj -scheme FamilyOS -sdk iphonesimulator \
  -destination 'generic/platform=iOS Simulator' -derivedDataPath build \
  CODE_SIGN_STYLE=Manual CODE_SIGN_IDENTITY=- DEVELOPMENT_TEAM="" PROVISIONING_PROFILE_SPECIFIER="" \
  build "$@" | grep -E "error:|warning: .*\.swift|BUILD (SUCCEEDED|FAILED)" || true
