#!/bin/sh
# Builds the 32K cartridge ROM (four 8K banks, non-inverted: the Classic99 /
# FinalGROM99 / ti99-headless name ends in 8) from apeterm.a99:
#   build.sh           APETERM8.bin    English
#   build.sh it [out]  APETERMI8.bin   Italian (-D ITALIAN), or the file out
# Needs xdt99's xas99.py: XDT99 = its folder (default: xas99.py on the PATH).
set -e
cd "$(dirname "$0")"
XAS=${XDT99:+$XDT99/}xas99.py
XAS=$(command -v $XAS || echo $XAS)
python3 font.py > font.a99
python3 font64.py > font64.a99
python3 inverse.py 0 > inv0.a99
python3 inverse.py 1 > inv1.a99
W=$(mktemp -d)
if [ "$1" = it ]; then
    OUT=${2:-APETERMI8.bin}
    python3 "$XAS" -R -b -q -D ITALIAN -o "$W/r.bin" apeterm.a99
else
    OUT=APETERM8.bin
    python3 "$XAS" -R -b -q -o "$W/r.bin" -L apeterm.lst apeterm.a99
fi
python3 - "$W" "$OUT" <<'PY'
import os, sys
w, name = sys.argv[1], sys.argv[2]
out = b""
for bank in range(4):
    d = open(os.path.join(w, "r_b%d.bin" % bank), "rb").read()
    assert len(d) <= 8192, "%s bank %d too large: %d bytes" % (name, bank, len(d))
    print("%s bank %d: %d bytes used, %d free" % (os.path.basename(name), bank, len(d), 8192 - len(d)))
    out += d + b"\xff" * (8192 - len(d))
open(name, "wb").write(out)
PY
rm -rf "$W"
