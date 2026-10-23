#!/bin/sh
# Archive and export the app for TestFlight or the store.
#   DEVELOPMENT_TEAM=XXXXXXXXXX ./release.sh
# Needs the paid Apple Developer Program for TestFlight; a personal team can
# only install on its own phones from Xcode. The team id is on Xcode's
# Accounts screen. Signing is automatic: Xcode makes the profiles.
set -eu
cd "$(dirname "$0")"
: "${DEVELOPMENT_TEAM:?set DEVELOPMENT_TEAM to your 10-character team id}"
xcodegen generate --quiet
xcodebuild -project FamilyOS.xcodeproj -scheme FamilyOS -configuration Release \
  -destination 'generic/platform=iOS' -archivePath build/FamilyOS.xcarchive \
  DEVELOPMENT_TEAM="$DEVELOPMENT_TEAM" -allowProvisioningUpdates archive | grep -E "error:|ARCHIVE" || true
xcodebuild -exportArchive -archivePath build/FamilyOS.xcarchive -exportPath build/export \
  -exportOptionsPlist ExportOptions.plist -allowProvisioningUpdates | grep -E "error:|EXPORT" || true
ls -la build/export 2>/dev/null || echo "no export: read the errors above"
