# APEDSK99 mod – virtual PIO / RS232 printer

A modification of [APEDSK99](https://github.com/jambuur/APEDSK99) by Jochen Buur, the Arduino-based disk controller for the TI-99/4A.

It adds a second DSR, **APEDSKPR**, that emulates a printer on `PIO` and `RS232`. Whatever the TI prints goes to a file on the SD card, and when the file is closed it is sent to the FTP server already configured for APEDSK99.

## Contents

| Path | What it is |
|---|---|
| `SD/APEDSK99.DSR` | original v12s DSR |
| `SD/APEDSKPR.DSR` | new DSR (v12p) with the virtual printer |
| `SD/CALLHLPP.TXT` | help screen for the new DSR (`CALL AHLP`) |
| `TI/APEDSK99.a99` | source of the original DSR |
| `TI/APEDSKPR.a99` | source of the new DSR |
| `Arduino/APEDSK99_012s/` | Arduino sketch with the printer commands added |

The first commit holds the original files unchanged, so a `git diff` against it shows exactly what was modified.

## The APEDSKPR DSR

The DSR space was almost full, so to make room for the printer this DSR keeps only the essential CALLs:

- **kept:** `LDSK`, `MDSK`, `AHLP`, `ADSR`, `CDIR`, `SMAP`, `LDIR` (plus `CALL FILES`)
- **removed:** `PDSK`, `UDSK`, `NDSK`, `RDSK`, `FGET`, `FPUT`, `ACHR`, `ARST`, `TIME`, `ACFG`

`CALL AHLP` shows a single help screen for this DSR (`CALLHLPP.TXT`). For the removed CALLs, switch back to the standard DSR.

`CALL SMAP` lists the SD card folders in three columns instead of one per row. This change is in the firmware, so it applies to both DSRs.

## Installation

1. Copy `SD/APEDSKPR.DSR` and `SD/CALLHLPP.TXT` to the root of the SD card, next to `APEDSK99.DSR` and `CALLhlp.txt`.
2. Upload the sketch in `Arduino/APEDSK99_012s` to the Arduino Uno. It needs the libraries from the original project. The same firmware works with both DSRs: it reads the DSR version (`v12s` or `v12p`) to pick the right help file.

## Usage

```
CALL ADSR("APEDSKPR")     then FCTN-QUIT
```

```
OPEN #1:"PIO"
PRINT #1:"HELLO FROM THE TI-99"
CLOSE #1
```

`LIST "PIO"` works too, as does any program that prints to `PIO` or `RS232`.

- While printing, the output goes to `/PRINT.TXT` on the SD card.
- On `CLOSE` the file is sent via FTP as `PRINT-YYMMDD-HHMM.TXT`, using the time from NTP. Without NTP it is named `PRINT.TXT`. The TI pauses for a few seconds during the transfer.
- If the FTP server cannot be reached, `CLOSE` returns I/O error 6 and the file stays on the SD card. The next `OPEN` overwrites it.

### Options

By default the file is **raw**: every byte exactly as a real printer would receive it, with CR/LF at the end of each record. Options are added to the device name and can be combined, e.g. `PIO.TX` or `RS232.TX.LF`.

| Option | Effect |
|---|---|
| `.TX` | clean text: drops printer control codes (see below) |
| `.CR` | no CR at the end of each record |
| `.LF` | no LF at the end of each record |

`.CR` and `.LF` behave as on the real RS232 card. Other RS232 options (`.BA=9600`, `.DA=8`, …) are accepted and ignored. `RS232` is output only: there is no receive or modem support, and while APEDSKPR is loaded a real RS232 card is not reachable under that name.

**`.TX` filter:** keeps printable text, TAB, CR, LF and form feed. It drops other control characters (SO, SI, BEL, CAN, DEL…) and Epson ESC/P sequences, including their parameters and bit-image graphics data (`ESC K/L/Y/Z/*`). Characters with the high bit set (Epson italics) are printed as normal characters. Other printer families (Prowriter, Okidata) use mostly `ESC` plus one letter and are cleaned too, but may leave a few stray characters.

**Graphics:** in raw mode (usually with `.CR.LF`, as graphics programs expect) the file keeps the full bit-image data, so a printout can be rebuilt on a PC with an ESC/P converter such as [PrinterToPDF](https://github.com/RWAP/PrinterToPDF). Setting the TI program to an Epson printer gives the easiest file to convert.

### Back to the standard DSR

```
CALL ADSR("APEDSK99")     then FCTN-QUIT
```

**Note:** switching DSR restarts the Arduino, so `MDSK` mappings reset to `_APEDSK1/2/3.DSK`. The network configuration (IP, FTP, NTP) is kept in EEPROM.

**Default at power-on:** the DSR chosen with `ADSR` stays active only until the next power-on or press of the Arduino reset button. After that APEDSK99 always starts with the standard `APEDSK99.DSR`. (The original firmware keeps the last `ADSR` choice across power cycles.)

## How it works

The DSR adds `PIO` and `RS232` to the device chain after `DSK3`; both use the same handler. It sends one command per character: the character goes to the `CALLBF` buffer (>5FC8) and a command code to `ACOMND` (>5FE8). As with the other APEDSK99 CALLs, the Arduino then halts the TI, runs the command and releases it.

| Code | Command |
|---|---|
| >40 | OPEN: creates `/PRINT.TXT`; the option string from the device name is passed in `CALLBF`; if the PAB gives no record length, the DSR sets 80 |
| >41 | one character (in `CALLBF`) |
| >42 | end of record: CR/LF, unless `.CR` / `.LF` |
| >43 | CLOSE: closes the file and sends it via FTP |

Arduino errors are passed back through `CALLST` and become error 6 in the PAB. Unsupported opcodes return error 3.

## Building

- **DSR:** `xas99.py -R -b TI/APEDSKPR.a99 -o APEDSKPR.bin` ([xdt99](https://github.com/endlos99/xdt99)), then pad with zeros to 8192 bytes. Assembled the same way, the original source is byte-identical to `APEDSK99.DSR`. The DSR currently uses all but 134 bytes of its space.
- **Sketch:** Arduino IDE, board Uno. It uses about 97% of flash.

## Credits

APEDSK99 is the work of Jochen Buur ([github.com/jambuur/APEDSK99](https://github.com/jambuur/APEDSK99)), released as freeware without restrictions. The disk controller code is based on Thierry Nouspikel's commented disassembly.
