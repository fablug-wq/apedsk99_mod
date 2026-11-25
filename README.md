# APEDSK99 mod – virtual PIO printer

A modification of [APEDSK99](https://github.com/jambuur/APEDSK99) by Jochen Buur, the Arduino-based disk controller for the TI-99/4A.

It adds a second DSR, **APEDSKPR**, that emulates a `PIO` printer. Whatever the TI prints goes to a text file on the SD card, and when the file is closed it is sent to the FTP server already configured for APEDSK99.

## Contents

| Path | What it is |
|---|---|
| `SD/APEDSK99.DSR` | original v12s DSR |
| `SD/APEDSKPR.DSR` | new DSR with PIO |
| `TI/APEDSK99.a99` | source of the original DSR |
| `TI/APEDSKPR.a99` | source of the new DSR |
| `Arduino/APEDSK99_012s/` | Arduino sketch with the PIO commands added |

The first commit holds the original files unchanged, so a `git diff` against it shows exactly what was modified.

## The APEDSKPR DSR

The DSR space was almost full, so to make room for PIO this DSR keeps only the essential CALLs:

- **kept:** `LDSK`, `MDSK`, `ADSR`, `CDIR`, `SMAP`, `LDIR` (plus `CALL FILES`)
- **removed:** `PDSK`, `UDSK`, `NDSK`, `RDSK`, `FGET`, `FPUT`, `AHLP`, `ACHR`, `ARST`, `TIME`, `ACFG`

For the removed CALLs, switch back to the standard DSR.

## Installation

1. Copy `SD/APEDSKPR.DSR` to the root of the SD card, next to `APEDSK99.DSR`.
2. Upload the sketch in `Arduino/APEDSK99_012s` to the Arduino Uno. It needs the libraries from the original project. The same firmware works with both DSRs.

## Usage

```
CALL ADSR("APEDSKPR")     then FCTN-QUIT
```

```
OPEN #1:"PIO"
PRINT #1:"HELLO FROM THE TI-99"
CLOSE #1
```

`LIST "PIO"` works too, as does any program that prints to `PIO`.

- While printing, the output goes to `/PRINT.TXT` on the SD card, with CR/LF at the end of each record.
- On `CLOSE` the file is sent via FTP as `PRINT-YYMMDD-HHMM.TXT`, using the time from NTP. Without NTP it is named `PRINT.TXT`. The TI pauses for a few seconds during the transfer.
- If the FTP server cannot be reached, `CLOSE` returns I/O error 6 and the file stays on the SD card. The next `OPEN` overwrites it.

To go back to the standard DSR:

```
CALL ADSR("APEDSK99")     then FCTN-QUIT
```

**Note:** switching DSR restarts the Arduino, so `MDSK` mappings reset to `_APEDSK1/2/3.DSK`. The network configuration (IP, FTP, NTP) is kept in EEPROM.

## How it works

The DSR adds `PIO` to the device chain after `DSK3`. For each character it writes the character to the `CALLBF` buffer (>5FC8) and a command code to `ACOMND` (>5FE8). As with the other APEDSK99 CALLs, the Arduino then halts the TI, runs the command and releases it.

| Code | Command |
|---|---|
| >40 | OPEN: creates `/PRINT.TXT`; if the PAB gives no record length, the DSR sets 80 |
| >41 | one character (in `CALLBF`) |
| >42 | end of record: CR/LF |
| >43 | CLOSE: closes the file and sends it via FTP |

Arduino errors are passed back through `CALLST` and become error 6 in the PAB. Unsupported opcodes return error 3.

## Building

- **DSR:** `xas99.py -R -b TI/APEDSKPR.a99 -o APEDSKPR.bin` ([xdt99](https://github.com/endlos99/xdt99)), then pad with zeros to 8192 bytes. Assembled the same way, the original source is byte-identical to `APEDSK99.DSR`.
- **Sketch:** Arduino IDE, board Uno. It uses about 94% of flash.

## Credits

APEDSK99 is the work of Jochen Buur ([github.com/jambuur/APEDSK99](https://github.com/jambuur/APEDSK99)), released as freeware without restrictions. The disk controller code is based on Thierry Nouspikel's commented disassembly.
