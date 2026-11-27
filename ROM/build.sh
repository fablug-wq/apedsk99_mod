#!/bin/sh
# Builds the 8K cartridge ROMs (Classic99 / ti99-headless names) from tinet.a99:
#   TINETC.bin    English
#   TINETITC.bin  Italian (-D ITALIAN: text_it.a99)
# Needs xdt99's xas99.py: XDT99 = its folder (default: xas99.py on the PATH).
set -e
cd "$(dirname "$0")"
XAS=${XDT99:+$XDT99/}xas99.py
XAS=$(command -v $XAS || echo $XAS)
python3 font.py > font.a99
python3 "$XAS" -R -b -q -o TINETC.bin -L tinet.lst tinet.a99
python3 "$XAS" -R -b -q -D ITALIAN -o TINETITC.bin tinet.a99
python3 - <<'PY'
for name in ("TINETC.bin", "TINETITC.bin"):
    d = open(name, "rb").read()
    assert len(d) <= 8192, "%s too large: %d bytes" % (name, len(d))
    open(name, "wb").write(d + b"\xff" * (8192 - len(d)))
    print("%s: %d bytes used, %d free" % (name, len(d), 8192 - len(d)))
PY
