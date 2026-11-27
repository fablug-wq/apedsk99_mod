#!/bin/sh
# Flash/RAM of the sketch for an Arduino Uno, without the Arduino IDE.
# Needs: arduino-cli, ArduinoCore-avr in ~/Arduino/hardware/arduino/avr (with a
# platform.local.txt pointing compiler.path to avr-gcc), and the sketch libraries
# (Ethernet 2.0.x, SdFat 1.1.4, Industrial Shields FTP and NTP) in ~/Arduino/libraries.
# The text region is enlarged to 64K so an over-size build still links and can be measured.
# Absolute values are ~2 KB above the IDE's (different avr-gcc build): compare differences.
# usage: harness/size.sh [sketch_dir]
set -e
H=$(cd "$(dirname "$0")" && pwd)
SK=${1:-$H/../Arduino/APEDSK99_012n}
W=$(mktemp -d)
python3 "$H/inobuild.py" "$SK" "$W/build_sk" 2>/dev/null
arduino-cli compile --fqbn arduino:avr:uno --build-path "$W/bin" \
  --build-property "compiler.c.elf.extra_flags=-Wl,--defsym=__TEXT_REGION_LENGTH__=65536" "$W/build_sk" 2>&1 \
  | grep -v "^Error initializing" | grep -iE " error|undefined" || true
avr-size "$W/bin/build_sk.ino.elf" | awk 'NR==2{printf "flash %d  ram %d\n", $1+$2, $2+$3}'
rm -rf "$W"
