#!/bin/sh
# Builds firmware_server: the sketch + harness mocks + the co-simulation main.
# usage: harness/cosim/build.sh [output [sketch_dir]]
#   output: default harness/cosim/firmware_server; sketch_dir: default Arduino/APEDSK99_012n
set -e
H=$(cd "$(dirname "$0")/.." && pwd)
OUT=${1:-$H/cosim/firmware_server}
SK=${2:-$H/../Arduino/APEDSK99_012n}
W=$(mktemp -d)
N=$(basename "$SK")
mkdir -p "$W/sk/$N"
cp "$SK"/*.ino "$W/sk/$N/"
rm "$W/sk/$N/"*-B-HAL.ino
python3 "$H/inobuild.py" "$W/sk/$N" "$W/out" 2>/dev/null
g++ -std=gnu++17 -fpermissive -w -O1 -I"$H/include" "$W/out/all.cpp" "$H/mocks.cpp" "$H/cosim/firmware_server.cpp" -o "$OUT"
rm -rf "$W"
