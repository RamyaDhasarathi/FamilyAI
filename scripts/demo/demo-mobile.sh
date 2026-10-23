#!/bin/zsh
# Record the simulator while DemoTests walks the app, Photos and Shortcuts.
set -u
D=$(cd "$(dirname "$0")" && pwd); S=${DEMO_OUT:-$D/out}; mkdir -p "$S"; cd "$D/../.."
SIM=E11BA34C-3D35-44D5-A866-D298F8F9F5EF
( set -a; source .env; set +a; OUT="$S/link-sim.txt" .venv/bin/python "$D/demo-link.py" ) && echo "sim link issued"
cd ios && xcodebuild -project FamilyOS.xcodeproj -scheme FamilyOSDriver -destination "id=$SIM" -derivedDataPath build-demo build-for-testing 2>&1 | grep -E "error:|TEST BUILD (SUCCEEDED|FAILED)"
rm -f "$S/mobile.mp4"; xcrun simctl io $SIM recordVideo --codec h264 --force "$S/mobile.mp4" > "$S/record.log" 2>&1 &
REC=$!; date +%s.%N > "$S/record-start.txt"; sleep 2
TEST_RUNNER_FAMILYOS_DEMO=1 TEST_RUNNER_FAMILYOS_SIGNIN_LINK="$(cat "$S/link-sim.txt")" TEST_RUNNER_FAMILYOS_SERVER=http://127.0.0.1:8088 \
TEST_RUNNER_FAMILYOS_ERRAND=18866e5a-8890-43fd-b08b-79b93fc55807 TEST_RUNNER_FAMILYOS_CHILD=Sashreek TEST_RUNNER_FAMILYOS_NOTICE_WORD="Parent-Teacher" \
xcodebuild test-without-building -project FamilyOS.xcodeproj -scheme FamilyOSDriver -destination "id=$SIM" -derivedDataPath build-demo -only-testing:FamilyOSDriver/DemoTests > "$S/demo-test.log" 2>&1
echo "test exit $?"; sleep 2; kill -INT $REC; wait $REC 2>/dev/null; sleep 3
grep -E "DEMOMARK|DEMO |Failed: |TEST (SUCCEEDED|FAILED)" "$S/demo-test.log" | sed 's/lnk_[A-Za-z0-9_-]*/lnk_…/' | cut -c1-130
ffprobe -v error -show_entries format=duration -of csv=p=0 "$S/mobile.mp4"
echo "RUN DONE"
