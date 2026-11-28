# APEDSK99 mod – branch `bbs-terminal`: network terminal (work in progress)

A modification of [APEDSK99](https://github.com/jambuur/APEDSK99) by Jochen Buur, the Arduino-based disk controller for the TI-99/4A.

**This branch** adds to the firmware four commands that let a TI program connect to a telnet BBS (or any TCP service) through the APEDSK99 Ethernet shield, and **APEDSK TERMINAL**, a terminal cartridge that uses them. The `main` branch has the virtual printer only.

| Part | Status |
|---|---|
| Firmware commands >70–>73 (CONNECT, SEND, RECV, CLOSE) | done, tested in the PC harness and in the co-simulation; not yet tested on real hardware |
| APEDSK TERMINAL 1.0 (`ROM/APETERM8.bin`, English; 32K bank-switched cartridge, needs 32K; the Italian ROM with `ROM/build.sh it`; 0.2 for 8K loaders in `ROM/v0.2`) | 40 or 64 columns on the TMS9918 (64 in bitmap mode, Tasword 3 font), 80 × 25 with the 16 ANSI colours on the F18A; telnet, ANSI, CP437, inverse; XMODEM download and upload (TIFILES files keep their type); address book and options with LOAD / SAVE; local echo and CR LF for plain services; tested on the emulated console with the real firmware and DSR; not yet on real hardware |
| DSRs | unchanged: the commands work with both `APEDSK99.DSR` and `APEDSKPR.DSR` |

The firmware is compatible with the existing DSRs, and printing, `FGET`, `FPUT` and `TIME` keep working, also during a telnet session. It adds about 390 bytes of flash (about 440 left on the Uno). Details: [Network terminal commands](#network-terminal-commands-work-in-progress) below.

To try it without the hardware: `harness/run.sh` (needs g++ and Python 3), or the co-simulation in `harness/cosim` and `ROM/test_rom.py` (needs [ti99-headless](https://github.com/fablug-wq/ti99-headless) 0.2.0 or later). On the hardware: the Extended BASIC test program `NETTEST`, see [Hardware test](docs/BBS-terminal.md#hardware-test-nettest).

## The virtual printer (also in `main`)

The branch keeps everything from `main`: a second DSR, **APEDSKPR**, that emulates a printer on `PIO` and `RS232`. Whatever the TI prints goes to a file on the SD card, and when the file is closed it is sent to the FTP server already configured for APEDSK99.

## Contents

| Path | What it is |
|---|---|
| `SD/APEDSK99.DSR` | original v12s DSR |
| `SD/APEDSKPR.DSR` | new DSR (v12p) with the virtual printer |
| `SD/CALLHLPP.TXT` | help screen for the new DSR (`CALL AHLP`) |
| `TI/APEDSK99.a99` | source of the original DSR |
| `TI/APEDSKPR.a99` | source of the new DSR |
| `TI/NETTEST.xb`, `SD/DISKS/NETTEST.DSK` | Extended BASIC test terminal for the network commands, as source and on a disk image |
| `Arduino/APEDSK99_012n/` | Arduino sketch 0.12n: the original 0.12s with the printer and network terminal commands added |
| `harness/` | PC test harness: the sketch on mock hardware, a fake telnet BBS, flash measurement |
| `docs/BBS-terminal.md` | design notes for the network terminal (firmware and terminal program) |
| `docs/terminal-mockup.html` | the early mockups of the terminal screens |
| `docs/screenshots/` | APEDSK TERMINAL in the emulator |
| `ROM/` | APEDSK TERMINAL: source (`apeterm.a99`, `menu.a99`, `term.a99`, `xmodem.a99`), font and inverse generators, build script, tests, the ROM (`APETERM8.bin`; 0.2 in `v0.2/`) |
| `harness/cosim/` | co-simulation: the real firmware as the APEDSK99 card of an emulated TI |

The first commit holds the original files unchanged, so a `git diff` against it shows exactly what was modified.

## The APEDSKPR DSR

The DSR space was almost full, so to make room for the printer this DSR keeps only the essential CALLs:

- **kept:** `LDSK`, `MDSK`, `AHLP`, `ADSR`, `CDIR`, `SMAP`, `LDIR` (plus `CALL FILES`)
- **removed:** `PDSK`, `UDSK`, `NDSK`, `RDSK`, `FGET`, `FPUT`, `ACHR`, `ARST`, `TIME`, `ACFG`

`CALL AHLP` shows a single help screen for this DSR (`CALLHLPP.TXT`). For the removed CALLs, switch back to the standard DSR.

`CALL SMAP` lists the SD card folders in three columns instead of one per row. This change is in the firmware, so it applies to both DSRs.

## Installation

1. Copy `SD/APEDSKPR.DSR` and `SD/CALLHLPP.TXT` to the root of the SD card, next to `APEDSK99.DSR` and `CALLhlp.txt`.
2. Upload the sketch in `Arduino/APEDSK99_012n` to the Arduino Uno. It needs the libraries from the original project. The same firmware works with both DSRs: it reads the DSR version (`v12s` or `v12p`) to pick the right help file.

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

## Network terminal commands (work in progress)

Four firmware commands let a TI program open a TCP connection, for example to a telnet BBS. The terminal cartridge that uses them, APEDSK TERMINAL, and its design: `docs/BBS-terminal.md`. They need no DSR support: the program writes `CALLBF` and `ACOMND` directly, so they work with either DSR. Bytes are raw (no TI BASIC screen bias). The firmware is only a pipe: telnet negotiation and the screen are up to the TI program.

| Code | Command | TI → `CALLBF` | Result |
|---|---|---|---|
| >70 | CONNECT | `host[:port]` + >00, max 31 characters; host name or dotted IP; default port 23 | `CALLST` >FF ok, 2 = can't connect |
| >71 | SEND | [0] = n (1–31), [1..n] data | `CALLST` >FF ok, 2 = not connected |
| >72 | RECV | — | [0] = n (0 = nothing yet, >FF = connection closed), [1..n] data |
| >73 | CLOSE | — | `CALLST` >FF |

- The connection stays open between commands, and printing, `FGET`, `FPUT` and `TIME` can run during a session. The W5100 has 4 sockets: telnet, NTP, FTP control and FTP data use all of them during a transfer.
- A drop by the other side shows up as RECV = >FF once all received data has been read. Right after the drop SEND may still report success.
- Detecting older firmware: write >FE to `CALLBF` and send RECV. Older firmware ignores the command and leaves the >FE in place.

## APEDSK TERMINAL

Load `ROM/APETERM8.bin` as a 32K bank-switched cartridge (non-inverted, file name ending in 8) on a loader that takes one (FinalGROM99, a flash cartridge, an emulator); for 8K-only loaders, the older `ROM/v0.2/TINETC.bin`. With the 32K expansion and the firmware of this branch it appears as APEDSK TERMINAL in the menu. With an F18A it offers 80 columns and colours. Usage, keys, XMODEM and the file of LOAD / SAVE (`DSK1.APENET` by default): `docs/BBS-terminal.md`.

## Building

- **DSR:** `xas99.py -R -b TI/APEDSKPR.a99 -o APEDSKPR.bin` ([xdt99](https://github.com/endlos99/xdt99)), then pad with zeros to 8192 bytes. Assembled the same way, the original source is byte-identical to `APEDSK99.DSR`. The DSR currently uses all but 134 bytes of its space.
- **Sketch:** Arduino IDE, board Uno. It uses about 98.5% of flash.
- **APEDSK TERMINAL:** `ROM/build.sh` (xdt99's `xas99.py`; `XDT99` = its folder): fonts, inverse characters, assembly (four banks), padding and joining into 32K: `APETERM8.bin`; `ROM/build.sh it` for the Italian `APETERMI8.bin`.
- **PC harness:** `harness/run.sh` compiles the sketch with g++ against mock hardware (DSR RAM, SD card folder, Ethernet on host sockets, FTP folder, fixed NTP time) and tests the terminal commands against `harness/fake_bbs.py`, a fake telnet BBS. The hardware itself (timing, SPI, the W5100) is not simulated.

## Credits

APEDSK99 is the work of Jochen Buur ([github.com/jambuur/APEDSK99](https://github.com/jambuur/APEDSK99)), released as freeware without restrictions. The disk controller code is based on Thierry Nouspikel's commented disassembly.

The 64-column font of APEDSK TERMINAL (`ROM/font64.py`, `ROM/tasword.py`) is derived from Tasword 3 by Damien Guard ([damieng.com/typography/zx-origins](https://damieng.com/typography/zx-origins/)), licensed [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/); the derived font is under the same licence.
