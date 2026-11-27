#!/bin/sh
# Builds the APEDSK99 sketch on the PC (HAL replaced by harness/include + mocks.cpp),
# starts the fake BBS and runs the terminal test.   usage: harness/run.sh
set -e
H=$(cd "$(dirname "$0")" && pwd)
SK="$H/../Arduino/APEDSK99_012n"
W=$(mktemp -d)
N=$(basename "$SK")
mkdir -p "$W/sk/$N"
cp "$SK"/*.ino "$W/sk/$N/"
rm "$W/sk/$N/"*-B-HAL.ino
python3 "$H/inobuild.py" "$W/sk/$N" "$W/out" 2>/dev/null
g++ -std=gnu++17 -fpermissive -w -g -I"$H/include" "$W/out/all.cpp" "$H/mocks.cpp" "$H/test_terminal.cpp" -o "$W/test"

mkdir -p "$W/sd/DISKS" "$W/ftp"
cp "$H/../SD/APEDSK99.DSR" "$W/sd/"
python3 -c "import sys; sys.stdout.write(''.join(('* error %d' % i).ljust(16) for i in range(16)))" > "$W/sd/CALLerr.txt"
head -c 92160 /dev/urandom > "$W/ftp/TEST.DSK"

python3 "$H/fake_bbs.py" 2323 > "$W/bbs.log" 2>&1 &
BBS=$!
sleep 0.5
RC=0; cd "$W" && SDROOT="$W/sd" FTPROOT="$W/ftp" ./test || RC=$?
kill $BBS 2>/dev/null
echo "--- fake_bbs log"; cat "$W/bbs.log"
cmp -s "$W/ftp/TEST.DSK" "$W/sd/DISKS/TEST.DSK" && echo "FGET copy identical"
rm -rf "$W"
exit $RC
