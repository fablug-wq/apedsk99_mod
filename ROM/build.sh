#!/bin/sh
# Builds the 16K cartridge ROMs (two 8K banks, non-inverted: the Classic99 /
# FinalGROM99 / ti99-headless name ends in 8) from tinet.a99:
#   TINET8.bin    English
#   TINETI8.bin   Italian (-D ITALIAN)
# Needs xdt99's xas99.py: XDT99 = its folder (default: xas99.py on the PATH).
set -e
cd "$(dirname "$0")"
XAS=${XDT99:+$XDT99/}xas99.py
XAS=$(command -v $XAS || echo $XAS)
python3 font.py > font.a99
python3 font64.py > font64.a99
W=$(mktemp -d)
python3 "$XAS" -R -b -q -o "$W/en.bin" -L tinet.lst tinet.a99
python3 "$XAS" -R -b -q -D ITALIAN -o "$W/it.bin" tinet.a99
python3 - "$W" <<'PY'
import os, sys
w = sys.argv[1]
for lang, name in (("en", "TINET8.bin"), ("it", "TINETI8.bin")):
    out = b""
    for bank in (0, 1):
        d = open(os.path.join(w, "%s_b%d.bin" % (lang, bank)), "rb").read()
        assert len(d) <= 8192, "%s bank %d too large: %d bytes" % (name, bank, len(d))
        print("%s bank %d: %d bytes used, %d free" % (name, bank, len(d), 8192 - len(d)))
        out += d + b"\xff" * (8192 - len(d))
    open(name, "wb").write(out)
PY
rm -rf "$W"
