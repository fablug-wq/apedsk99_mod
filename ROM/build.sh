#!/bin/sh
# Builds TINETC.bin (8K cartridge ROM, Classic99 / ti99-headless name) from tinet.a99.
# Needs xdt99's xas99.py: XDT99 = its folder (default: xas99.py on the PATH).
set -e
cd "$(dirname "$0")"
XAS=${XDT99:+$XDT99/}xas99.py
python3 font.py > font.a99
python3 "$(command -v $XAS || echo $XAS)" -R -b -q -o TINETC.bin -L tinet.lst tinet.a99
python3 - <<'PY'
d = open("TINETC.bin", "rb").read()
assert len(d) <= 8192, "ROM too large: %d bytes" % len(d)
open("TINETC.bin", "wb").write(d + b"\xff" * (8192 - len(d)))
print("TINETC.bin: %d bytes used, %d free" % (len(d), 8192 - len(d)))
PY
