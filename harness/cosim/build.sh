#!/bin/sh
# Builds firmware_server: the sketch + harness mocks + the co-simulation main.
# usage: harness/cosim/build.sh [output]   (default harness/cosim/firmware_server)
set -e
H=$(cd "$(dirname "$0")/.." && pwd)
OUT=${1:-$H/cosim/firmware_server}
W=$(mktemp -d)
mkdir -p "$W/sk/APEDSK99_012s"
cp "$H/../Arduino/APEDSK99_012s"/*.ino "$W/sk/APEDSK99_012s/"
rm "$W/sk/APEDSK99_012s/APEDSK99_012s-B-HAL.ino"
python3 "$H/inobuild.py" "$W/sk/APEDSK99_012s" "$W/out" 2>/dev/null
g++ -std=gnu++17 -fpermissive -w -O1 -I"$H/include" "$W/out/all.cpp" "$H/mocks.cpp" "$H/cosim/firmware_server.cpp" -o "$OUT"
rm -rf "$W"
