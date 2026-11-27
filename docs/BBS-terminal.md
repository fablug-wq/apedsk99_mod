# Network terminal for telnet BBSes – design notes

Status, 27 November 2026: the **firmware side is done** and tested in the PC harness. Not yet tested on real hardware. The terminal program (cartridge ROM, working name *TI-NET TERM*) is not written yet; these notes describe what it should do.

Mockups of the screens: `docs/terminal-mockup.html` (open it in a browser).

## Why a dedicated program

Existing TI terminal programs (Telco, Fast-Term…) drive the TMS9902 of the RS232 card directly through CRU >1300. APEDSK99 does not decode the CRU and cannot emulate a 9902, so they can't use it. The only way to run them on a network is a real RS232 card plus a WiFi modem (ESP8266 with AT commands).

So the firmware offers a raw TCP pipe, and a program written for it does the rest. No DSR change: the program writes `CALLBF` and `ACOMND` directly, so it works with the standard DSR and with APEDSKPR.

## Firmware commands

| Code | Command | TI → `CALLBF` (>5FC8) | Result |
|---|---|---|---|
| >70 | CONNECT | `host[:port]` + >00, max 31 characters; host name or dotted IP; default port 23 | `CALLST` (>5FC6) >FF ok, 2 = can't connect |
| >71 | SEND | [0] = n (1–31), [1..n] data | `CALLST` >FF ok, 2 = not connected |
| >72 | RECV | — | [0] = n (0 = nothing yet, >FF = connection closed), [1..n] data |
| >73 | CLOSE | — | `CALLST` >FF |

Writing the code to `ACOMND` (>5FE8) runs the command: the Arduino halts the TI, executes, releases it, so the result is there at the next instruction. Bytes are raw, with no TI BASIC screen bias.

Facts that matter for the program:

- **Never trust `CALLBF[0]` blindly** after RECV: a value above 31 other than >FF means the firmware does not have the terminal commands.
- **Firmware detection** at start: write >FE to `CALLBF[0]`, send RECV. If >FE is still there, older firmware ignored the command.
- **A drop by the other side** shows up as RECV = >FF once all data has been read. Right after the drop SEND may still report success (the W5100 accepts data in CLOSE_WAIT).
- Every byte the TI writes into `CALLBF` also halts the TI for a moment (the Arduino sees the write and ignores it), so SEND costs a little more than RECV.
- The connection stays open between commands, also while printing, `FGET`, `FPUT` and `TIME` run. During an FTP transfer all 4 W5100 sockets are in use (telnet, NTP, FTP control, FTP data).
- If the network dies during a SEND, the Ethernet library can keep the TI halted until the TCP timeout.

### Implementation notes (firmware)

- `case 112…115` in `APEDSK99_012s-G-AD99cmd.ino`, using the global `client`, which was unused before. `EtherStop()` no longer calls `client.stop()`.
- `EtherStart()` is unchanged: with Ethernet 2.0.x, `W5100.init()` resets the chip only on the first call; later `Ethernet.begin()` calls only rewrite MAC/IP/gateway/subnet, and open sockets survive.
- The shared pin (`ETH_CS` = `TI_INT`, PD2, active low) already selected the W5100 on every TI write before this change, without SPI clock, so with no effect. Nothing changes electrically.
- Status codes are written to `CALLST` directly: `CALLstatus()` with an error code would overwrite `CALLBF` with the error text.
- Cost: about +390 bytes of flash (about 440 left), no static RAM; 32 bytes of stack during the command.

## The terminal program

### Start-up

1. Chosen from the cartridge menu.
2. Silent checks: firmware (sentinel, above) and F18A.
3. Firmware without the terminal: an error screen that says so, and nothing else.
4. Otherwise the **address book** screen: pick an entry with its number + ENTER, or type `host[:port]`.
5. During a session FCTN-9 opens a menu: hang up, options, back to the address book.

A modem-style command prompt (`ATDT host:port`) could be added later as a second way in.

### Address book and options: a file on disk

ROM is read-only and RAM is lost at power-off, so the address book and the options are kept **in a file on disk** (name to be decided, e.g. `DSK1.BBSLIST`), read and written with the normal DSR file calls. This costs no Arduino flash and works with both DSRs; the ROM needs a small DSRLNK and PAB handling.

Options: columns (40 / 80 with F18A), palette, status line on/off, local echo (auto = from the server), what ENTER and BACK send.

### Telnet

A working prototype is the `Telnet` struct in `harness/test_terminal.cpp`.

- Server WILL ECHO and WILL SGA → answer DO (otherwise no echo and no character mode).
- Server DO TTYPE → WILL TTYPE; on SB TTYPE SEND answer SB TTYPE IS `ANSI`.
- Server DO NAWS → WILL NAWS + SB NAWS with the screen size.
- Anything else: WONT / DONT. DONT / WONT from the server: no answer.
- IAC IAC = one >FF data byte.

### Screen

- 40 columns on the TMS9918 (text mode), 80 columns optional with an F18A.
- **Status line:** if it is on, it takes the last row, so NAWS must report **40×23** (or 80×23), not 24. On the 9918 it can't be drawn in reverse video without a second, inverted copy of the characters, so it is separated by a line instead.
- ANSI subset (ECMA-48, ANSI.SYS flavour): cursor `A B C D`, `H`/`f`, `s`/`u`; erase `2J`, `K`; SGR 0, 1, 5, 7, 30–37, 40–47; answer `ESC[6n` with `ESC[row;colR` (many BBSes use it to detect ANSI).
- CP437 characters 128–255 (frames, blocks, shades): a table of 6×8 patterns in the ROM, indexed directly by the received byte.
- Colours: ignored on the 9918 (text mode has one colour pair for the whole screen); full on the F18A (per-position attributes).
- ANSI BBSes expect 25 rows; the TI has 24.

### Speed

Up to 31 bytes per exchange, an estimated 1–1.5 ms each on the hardware, so well above 9600 baud. Drawing on screen is the limit.

## Testing

- `harness/run.sh`: compiles the sketch with g++ against mock hardware (DSR RAM array, SD card folder, Ethernet on host sockets with the 4-socket limit and the reset-on-first-`begin` behaviour, FTP folder, fixed NTP time) and runs `harness/test_terminal.cpp` against `harness/fake_bbs.py`, a fake telnet BBS. 31 checks; with the previous firmware 13 pass. Timing, SPI and the W5100 itself are not simulated.
- `harness/size.sh`: flash and RAM of the sketch without the IDE.
- On the hardware, before the ROM: an Extended BASIC program with 32K. `CALL INIT`, `CALL LOAD(24520, …)` to fill `CALLBF`, `CALL LOAD(24552, 112)` for CONNECT, then in a loop `CALL LOAD(24552, 114)` and `CALL PEEK(24520, N)`, `CALL PEEK(24521, …)` for RECV.

## Hardware test: `NETTEST`

A small Extended BASIC terminal to check the firmware on the real machine before the ROM exists. Source `TI/NETTEST.xb`, ready on the disk image `SD/DISKS/NETTEST.DSK` (tokenized with xdt99 `xbas99.py -c`, disk made with `xdm99.py`).

It does: a firmware check (CLOSE, then RECV with the >FE sentinel), CONNECT to the address you type, then a loop of keyboard → SEND and RECV → screen. Telnet: DO to WILL ECHO / WILL SGA, DONT / WONT to everything else (no TTYPE / NAWS: that is for the ROM). ESC sequences are skipped, characters outside 32–126 are dropped, lines wrap at 28 columns. FCTN-9 closes the connection. It counts the bytes received.

Steps:

1. Upload the sketch from this branch to the Arduino.
2. Copy `NETTEST.DSK` into the `DISKS` folder of the SD card.
3. Extended BASIC with 32K: `CALL MDSK(1,"NETTEST")`, then `RUN "DSK1.NETTEST"`.
4. At `HOST[:PORTA]?` type a BBS address, or the PC running the fake BBS: `python3 harness/fake_bbs.py 2323 0.0.0.0` on the PC, `192.168.1.x:2323` on the TI.

What to check:

- the firmware is recognised and CONNECT works, with a host name and with a dotted IP;
- the banner appears and what you type comes back as echo;
- the session survives other APEDSK99 network commands: press FCTN-4 (BREAK), run `CALL TIME`, then `CON`, and keep typing;
- `QUIT` on the fake BBS: the program reports the connection closed by the other side.

Extended BASIC handles a few dozen bytes per second, so `BIG` (5000 bytes) on the fake BBS takes a while: it checks the data still arrives complete, not the speed. The speed of the firmware itself needs the ROM, or a small assembly loop.
