# Network terminal for telnet BBSes – design notes

Status, 27 November 2026:

- **firmware:** done, tested in the PC harness and in the co-simulation (below);
- **TI-NET TERM 0.1**, the terminal cartridge (`ROM/`): written in assembly, 40 columns, tested on the emulated console against the real firmware and DSR;
- **real hardware:** not tested yet.

Screenshots from the emulator: `docs/screenshots/`. The early mockups: `docs/terminal-mockup.html`.

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

## The terminal program: TI-NET TERM 0.1

An 8K cartridge ROM (`ROM/TINETC.bin`, source `ROM/tinet.a99`, font `ROM/font.py`). It needs the 32K memory expansion and the firmware of this branch, and works with either APEDSK99 DSR.

### Using it

1. Choose TI-NET TERM from the cartridge menu.
2. It checks the firmware (CLOSE, then RECV with the sentinel). Older firmware, or no APEDSK99: a screen that says so, and any key goes back to the title screen.
3. The **address book**: type `host[:port]` and ENTER, or choose an entry with FCTN-E / FCTN-X (up / down) and ENTER.
   - FCTN-8 saves the address typed in the field as a new entry (it asks the name, up to 14 characters).
   - FCTN-3 deletes an entry (it asks which one).
   - FCTN-9 opens the options, FCTN-= goes back to the title screen.
4. During a session: what you type goes to the BBS. FCTN-9 opens the menu on the status row: R hangs up and goes back to the address book, any other key carries on. When the BBS hangs up, the status row says so and any key goes back.

Keys in a session:

| Key | Sends |
|---|---|
| ENTER | CR (>0D) |
| FCTN-S | BS (>08) |
| FCTN-1 (DEL) | DEL (>7F) |
| FCTN-7 (AID) | ESC (>1B) |
| FCTN-E / X / D | ESC [ A / B / C (up, down, right) |
| CTRL-A … CTRL-Z | >01 … >1A |

### Address book and options: `DSK1.BBSLIST`

ROM is read-only and RAM is lost at power-off, so the address book and the options are kept **in a file on disk**, read and written through the normal DSR file calls (the ROM has its own DSRLNK). This costs no Arduino flash and works with both DSRs.

`DSK1.BBSLIST` is DIS/VAR 80: first `#P<palette>S<status row>` (e.g. `#P0S1`), then one record per entry, `name|host[:port]`, at most 9. It can be made on a PC too (a text file put on the disk image with xdm99). Without the file the address book starts empty; the first save creates it.

Options (FCTN-9 in the address book; saved when you leave the screen):

- palette: white on blue, green on black, black on cyan;
- status row: on (the BBS gets 23 rows) or off (24 rows);
- 40 columns only in this version; 80 columns with the F18A are planned.

### Telnet

As implemented in `TNBYTE` (the `Telnet` struct in `harness/test_terminal.cpp` is the same logic in C++):

- Server WILL ECHO and WILL SGA → answer DO (otherwise no echo and no character mode).
- Server DO TTYPE → WILL TTYPE; on SB TTYPE SEND answer SB TTYPE IS `ANSI`.
- Server DO NAWS → WILL NAWS + SB NAWS with the screen size.
- Anything else: WONT / DONT. DONT / WONT from the server: no answer.
- IAC IAC = one >FF data byte.

### Screen

- 40 columns, TMS9918 text mode. Characters 32–95 come from the console GROM (>06B4), 96–255 from the ROM: true lower case, CP437 accented letters, box drawing (single, double, mixed), blocks, shades, some symbols.
- **Status row** (row 24, optional): the host, `ANSI 40x23`, the connection time, `F9 MENU`. With it the BBS gets 23 rows (NAWS 40×23).
- ANSI: cursor `A B C D G d`, `H`/`f`, `s`/`u` and `ESC 7`/`ESC 8`; erase `J` (0, 1, 2) and `K` (0, 1, 2); `ESC[6n` answered with `ESC[row;colR`; `ESC c` clears. SGR (`m`) and private sequences (`ESC[?…`) are read and ignored: text mode has one colour pair for the whole screen. Line wrap is deferred to the next character, as on a VT100.
- The cursor is a block drawn while no data arrives.
- ANSI BBSes expect 25 rows; the TI has 24.
- Planned: 80 columns and colours with the F18A; inverse video.

KSCAN restores VDP register 1 from >83D4 at every key (to undo the screen saver): the ROM puts its own value (text mode) there, or the first key would switch the screen back to graphics mode.

### Speed

Measured in the emulator: about 46,000 CPU cycles for a packet of 31 bytes (about 1,500 a byte, more when the screen scrolls), so about 2 KB a second at 3 MHz, twice 9600 baud, before the time the Arduino takes for each RECV (estimated 1–1.5 ms). KSCAN costs about 2,500 cycles and runs once a loop.

## Testing

- `harness/cosim/`: **co-simulation**. The real sketch runs as a process (`firmware_server`) and is the firmware of an APEDSK99 card in an emulated TI-99/4A ([ti99-headless](https://github.com/fablug-wq/ti99-headless) 0.2.0 or later: js99er with the real console ROM and GROM). Every word the TI writes into >4000–>5FFF runs `loop()` once, as the GAL signals on the hardware (A15 = 0: once per word), and the TI waits meanwhile. So the real DSR (disks, CALLs) and the terminal commands run as on the machine, with the SD card and FTP server as folders and the network through the host. `test_cosim.py`: TI BASIC SAVE/OLD; `NETTEST` in Extended BASIC against the fake BBS.
- `ROM/test_rom.py`: TI-NET TERM in the co-simulation, 8 tests: the address book screen; a session (negotiation, ANSI and CP437 on screen, the ANSI test page with `ESC[6n`, the codes the keys send, FCTN-9 R); 5000 bytes; the BBS hanging up; a refused connection; saving, reading back, choosing and deleting entries in `DSK1.BBSLIST`; the options (palette, status row → NAWS 40×24, kept on disk); the firmware of `main` (the ROM says it lacks the commands). `ROM/screenshots.py` makes `docs/screenshots/`.

  ```
  TI99HEADLESS=/path/to/ti99-headless XDT99=/path/to/xdt99 python3 ROM/test_rom.py -v
  ```

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
