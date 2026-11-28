# Network terminal for telnet BBSes – design notes

Status, 28 November 2026:

- **firmware:** done, tested in the PC harness and in the co-simulation (below);
- **APEDSK TERMINAL 1.0**, the terminal cartridge (`ROM/`): written in assembly; 40 or 64 columns on the TMS9918, 80 × 25 with colours on the F18A; XMODEM download and upload; tested on the emulated console against the real firmware and DSR;
- **real hardware:** version 0.2 connected to a BBS on Fabrizio's machine; 1.0 not tested yet.

Screenshots from the emulator: `docs/screenshots/`. The early mockups: `docs/terminal-mockup.html` (open it in a browser).

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

- `case 112…115` in `APEDSK99_012n-G-AD99cmd.ino`, using the global `client`, which was unused before. `EtherStop()` no longer calls `client.stop()`.
- `EtherStart()` is unchanged: with Ethernet 2.0.x, `W5100.init()` resets the chip only on the first call; later `Ethernet.begin()` calls only rewrite MAC/IP/gateway/subnet, and open sockets survive.
- The shared pin (`ETH_CS` = `TI_INT`, PD2, active low) already selected the W5100 on every TI write before this change, without SPI clock, so with no effect. Nothing changes electrically.
- Status codes are written to `CALLST` directly: `CALLstatus()` with an error code would overwrite `CALLBF` with the error text.
- Cost: about +390 bytes of flash (about 440 left), no static RAM; 32 bytes of stack during the command.

## The terminal program: APEDSK TERMINAL 1.0

A 32K bank-switched cartridge ROM: four 8K banks, non-inverted (a write to >6000 + 2 × n selects bank n), file name ending in 8:

- `ROM/APETERM8.bin`: English.
- The Italian ROM comes from the same source: `ROM/build.sh it` makes `ROM/APETERMI8.bin` (not kept in the repository; the tests build it to check the Italian texts).
- Older versions: `ROM/v0.2/` (8K, 40 columns, `DSK1.BBSLIST`), for loaders without banks.

Sources:

- `ROM/apeterm.a99`: equates, variables, and the code the banks share (header, start, network calls, keyboard, VDP, DSRLNK, the PAB, the disk DSR's subprograms);
- `ROM/menu.a99`, bank 0: address book, options, LOAD / SAVE, the firmware check and the F18A check;
- `ROM/term.a99` and `ROM/xmodem.a99`, bank 1: telnet, ANSI, the screen, XMODEM;
- bank 2: the 64-column font, copied to the 32K (>A000) when a 64-column session starts;
- texts in `ROM/text_*.a99` (menus) and `ROM/term_*.a99` (session);
- generated: `font.a99` (`font.py`, 40/80 columns), `font64.a99` (`font64.py`), `inv0.a99` and `inv1.a99` (`inverse.py`).

It needs the 32K memory expansion and the firmware of this branch, and works with either APEDSK99 DSR. In the cartridge menu it is APEDSK TERMINAL. The screens below are named as in the English ROM.

### Using it

1. Choose APEDSK TERMINAL from the cartridge menu.
2. It checks the firmware (CLOSE, then RECV with the sentinel). Older firmware, or no APEDSK99: a screen that says so, and any key goes back to the title screen. It also checks for an F18A.
3. The **address book** starts empty with the default options: nothing is read from disk until LOAD.
   - Type `host[:port]` and ENTER, or choose an entry with FCTN-E / FCTN-X (up / down) and ENTER.
   - A host without `:port`: `PORT:` is asked below the field, `(default=23)`; ENTER on an empty field takes 23, FCTN-9 gives up.
   - FCTN-8 adds the address typed in the field as a new entry: the port if it has none, then the name (up to 14 characters).
   - FCTN-3 deletes an entry (it asks which one).
   - FCTN-5 LOAD and FCTN-6 SAVE: the address book and the options, from or to the file named on the row that appears, `DSK1.APENET` at first, then the last name used. ENTER does it, FCTN-9 gives up. Adding and deleting change only the list in memory until SAVE.
   - FCTN-9 opens the options.
   - FCTN-= (here, in the options, in a session) leaves: it hangs up if needed and puts the F18A back as at power-up (unlocked, the 9918 palette, its registers reset), so the title screen and whatever runs next find it clean.
4. During a session: what you type goes to the BBS. FCTN-9 opens the menu on the status row:
   - H hangs up and goes back to the address book (in both languages);
   - D downloads, U uploads a file (XMODEM, below);
   - Q hangs up and leaves, as FCTN-=;
   - any other key carries on.

   When the BBS hangs up, the status row says so and any key goes back.

Keys in a session:

| Key | Sends |
|---|---|
| ENTER | CR (>0D), or CR LF (>0D >0A) with the option |
| FCTN-S | BS (>08) |
| FCTN-1 (DEL) | DEL (>7F) |
| FCTN-7 (AID) | ESC (>1B) |
| FCTN-E / X / D | ESC [ A / B / C (up, down, right) |
| CTRL-A … CTRL-Z | >01 … >1A |

### Address book and options: LOAD and SAVE

ROM is read-only and RAM is lost at power-off, so the address book and the options are kept **in a file on disk**, read and written through the normal DSR file calls (the ROM has its own DSRLNK). This costs no Arduino flash and works with both DSRs. Nothing is read or written unless asked: LOAD and SAVE always handle both, and always show the file name before touching the disk.

The file is DIS/VAR 80: first the options, `#P<palette>S<status row>E<echo>N<ENTER>C<columns>A<ANSI colours>` (e.g. `#P0S1E0N0C2A1`; a missing letter keeps its default, so older files, `DSK1.BBSLIST` of 0.2 and 0.3 included, still load), then one record per entry, `name|host[:port]`, at most 9. It can be made on a PC too (a text file put on the disk image with xdm99). If the file cannot be read or written (no disk, no file, protected, full), the screen says `Disk error.` and nothing in memory changes. A file saved with 80 columns, loaded on a console without F18A, gives 40 columns.

Options (FCTN-9 in the address book; 1–6 change them; they last for the session, SAVE keeps them):

- palette: white on blue, green on black, black on cyan;
- status row: on (the BBS gets 23 rows) or off (24 rows); in 80 columns the BBS has 25 rows either way;
- local echo: AUTO (default: on while the server has not said WILL ECHO, so off with BBSes, on with plain services), on, off;
- ENTER sends: CR (default, what BBSes expect) or CR LF (what POP3, SMTP and most line-based services want);
- columns: 40 (text mode), 64 (bitmap mode), 80 (only with an F18A: the option skips it otherwise);
- ANSI colours: yes (default) or no, for 80 columns: the 16 ANSI colours, or the two of the palette.

The options screen says whether an F18A was found.

### Telnet

As implemented in `TNBYTE` (the `Telnet` struct in `harness/test_terminal.cpp` is the same logic in C++):

- Server WILL ECHO and WILL SGA → answer DO (otherwise no echo and no character mode). WILL ECHO / WONT ECHO also switch the AUTO local echo off / on.
- Server DO TTYPE → WILL TTYPE; on SB TTYPE SEND answer SB TTYPE IS `ANSI`.
- Server DO NAWS → WILL NAWS + SB NAWS with the screen size.
- Anything else: WONT / DONT. DONT / WONT from the server: no answer.
- IAC IAC = one >FF data byte.
- During a file transfer: IAC WILL BINARY and IAC DO BINARY at the start, WONT / DONT at the end; >FF is doubled out and undone in, the other commands are skipped.

### Screen

- **40 columns**: TMS9918 text mode. Characters 32–95 come from the console GROM (>06B4), 96–255 from the ROM: true lower case, CP437 accented letters, box drawing (single, double, mixed), blocks, shades, some symbols. The GROM's 7 rows go into rows 0–6 of the pattern (not 1–7, as the console does), so capitals, digits and lower case share one baseline (row 6) and the descenders of g, p, q, y use row 7; the accented capitals are drawn on the same baseline with the accent on row 0.
- **64 columns**: TMS9918 bitmap mode (graphics II), 4×8-pixel cells, two per 8×8 pattern, on the plain VDP. Font: [Tasword 3](https://damieng.com/typography/zx-origins/tasword/) by Damien Guard, licensed CC BY-SA 3.0, from its ZX Spectrum 64-column original; accented letters, `` ` ``, `^` and box drawing added in `ROM/font64.py`. The colour table is 2K shared by the three thirds of the screen (R3 = >9F), so the disk buffers at the top of VDP RAM stay untouched. Two colours. Writing a character is a read-modify-write of 8 bytes, so this mode is slower (see Speed).
- **80 columns (F18A)**: the F18A's 80-column text mode, unlocked, with 30 rows (R49 >40): 25 for the BBS (NAWS 80×25, as the PC screens ANSI art is drawn for), the status row, 4 blank. A colour byte for each position (R50 >02, foreground in the high nibble): names at >0000, patterns at >2000 (the 40-column font, copied), colours at >2800. With ANSI colours the F18A palette gets the 16 colours of the PC (the 9918 palette is put back when the session ends, and the F18A's registers are reset, which also locks it again); without them the two colours of the palette option. The F18A is detected at start: unlocked, status register 1 = >E0, then its registers reset; on a 9918 those writes land in registers that the menus set again. A write to VR57 while the F18A is unlocked locks it, so every unlock starts with VR50 >80 (unlocked: registers reset and locked; locked: ignored), then >1C twice: this way it works whatever state a previous program or a soft reset left.
- **Inverse (SGR 7, 27)**: in 80 columns the two colours of the position are swapped. In 64 columns the cell is inverted. In 40 columns every code 32–255 already has a glyph, so inverse uses the 49 codes never drawn (0–31, 127 and the empty places of the font): the space, the capitals, the digits and `. , : ; - ! ? / ( ) ' >`. A lower-case letter in inverse shows as its capital in inverse, as on the terminals of the time; other characters show as they are (`ROM/inverse.py`).
- **Colours (SGR 30–37, 40–47, 39, 49, 1, 22, 0)**: 80 columns only; bold is the bright colour. In 40 and 64 columns they are read and ignored. Erasing uses the current colours.
- **Status row** (optional): the host, `ANSI 40x23`, `ANSI 64x23` or `ANSI 80x25`, the connection time, `F9 MENU`; in the default colours. With it the BBS gets 23 rows in 40 and 64 columns.
- ANSI: cursor `A B C D G d`, `H`/`f`, `s`/`u` and `ESC 7`/`ESC 8`; erase `J` (0, 1, 2) and `K` (0, 1, 2); `ESC[6n` answered with `ESC[row;colR`; `ESC c` clears and resets the colours. Private sequences (`ESC[?…`) are read and ignored. Line wrap is deferred to the next character, as on a VT100.
- The cursor is a block drawn while no data arrives.

KSCAN restores VDP register 1 from >83D4 at every key (to undo the screen saver): the ROM puts its own value (text or bitmap mode) there, or the first key would switch the screen back to graphics mode.

### File transfers: XMODEM

FCTN-9 in a session, then D (download) or U (upload). The file name is asked on the status row, `DSK1.` at first, then the last one used: `DSKn.NAME`, a drive 1–9 and a name of 1–10 characters. While it runs the status row shows the blocks done; FCTN-9 stops it (CAN CAN CAN). At the end it says `Done.`, `Failed.` or `Cancelled.` with the blocks, and any key goes back to the session.

- **Download**: start the BBS's XMODEM send (CRC, checksum or 1K), then D. The ROM sends `C` (CRC) every 3 seconds; after four tries without an answer it switches to checksum (NAK). Blocks of 128 (SOH) and 1024 (STX) are both taken. If the file is on the disk already, it asks `Replace it? Y/N` and deletes it first.
  - A file that starts with a **TIFILES** header (what TI files on BBSes are) becomes a TI file of the type in the header: the header's fields (sectors, flags, records per sector, EOF offset, record length, records) are exactly those of subprogram >15 of the disk DSR ("file direct output", APEDSK99's DSR has it, as TI's), which creates the file, then gets its sectors one at a time. PROGRAM, DIS/VAR, INT/FIX…: all of them, with no buffer the size of the file.
  - Any other file becomes DIS/FIX 128, a record a 128 bytes; XMODEM pads the last block (with >1A), and the padding stays.
- **Upload**: start the BBS's XMODEM receive, then U. Subprogram >14 ("file direct input") gives the file's sectors and the fields of its header, and the ROM sends it as TIFILES, blocks of 128, CRC or checksum as the receiver asks (`C` or NAK), waiting up to a minute for it.
- The tests take a file to the TI and back to the BBS in both block sizes, and compare it with the original byte by byte.

### Speed

Measured in the emulator: about 46,000 CPU cycles for a packet of 31 bytes in 40 columns (about 1,500 a byte, more when the screen scrolls), so about 2 KB a second at 3 MHz, twice 9600 baud, before the time the Arduino takes for each RECV (estimated 1–1.5 ms). KSCAN costs about 2,500 cycles and runs once a loop.

In 64 columns: about 125,000 cycles for a packet of 31 bytes (about 4,000 a byte), so about 750 bytes a second; a scroll copies 23 × 256 bytes through CPU RAM and adds about 390,000 cycles (0.13 s).

In 80 columns (F18A): about 55,000 cycles for a packet of 31 bytes (each character writes its colour byte too: about 1,800 a byte, 1.7 KB a second); a scroll copies 24 rows of names and of colours, up to about 320,000 cycles (0.1 s).

XMODEM in the emulator: 896 bytes (a TIFILES file of 3 sectors, 7 blocks) in about 1.3 seconds, with blocks of 128 or 1K, sectors written on the disk included: about 700 bytes a second. On the hardware the Arduino's time for each RECV and for the SD card comes on top.

## Testing

- `harness/cosim/`: **co-simulation**. The real sketch runs as a process (`firmware_server`) and is the firmware of an APEDSK99 card in an emulated TI-99/4A ([ti99-headless](https://github.com/fablug-wq/ti99-headless) 0.2.0 or later: js99er with the real console ROM and GROM). Every word the TI writes into >4000–>5FFF runs `loop()` once, as the GAL signals on the hardware (A15 = 0: once per word), and the TI waits meanwhile. So the real DSR (disks, CALLs) and the terminal commands run as on the machine, with the SD card and FTP server as folders and the network through the host. `test_cosim.py`: TI BASIC SAVE/OLD; `NETTEST` in Extended BASIC against the fake BBS (the Extended BASIC cartridge: `XB_CART`, or the one ti99-headless carries from 0.2.3, `cartridge("extended_basic")`). Last run on ti99-headless 0.2.3.
- `ROM/test_rom.py`: APEDSK TERMINAL in the co-simulation, 17 tests:
  - the address book screen;
  - a session: negotiation, ANSI and CP437 on screen, the ANSI test page with `ESC[6n`, the codes the keys send, FCTN-9 H;
  - 5000 bytes; the BBS hanging up; a refused connection;
  - local echo AUTO with a BBS that stops and restarts echoing; a plain TCP service (the fake BBS in raw mode) with ENTER = CR LF and echo AUTO, then off;
  - the address book: adding, SAVE (FCTN-9 writes nothing), nothing read at start, LOAD, choosing, deleting, a file that is not there (nothing lost);
  - the port: asked for a host without one, 23 when empty, FCTN-9;
  - the options: palette, status row → NAWS 40×24, no 80 columns without F18A, defaults again when not saved, kept by SAVE and LOAD;
  - inverse in 40 columns (the codes and their patterns);
  - 64 columns: bitmap registers, NAWS 64×23, the ANSI page read back from the bitmap, inverse, scrolling, back to text mode;
  - 80 columns with the F18A: registers, NAWS 80×25, the colour byte of each position (ANSI colours, bold, background, inverse), the ANSI page, scrolling, back to 40 columns; then two colours;
  - XMODEM: TIFILES download in blocks of 128 and 1K (the second time replacing the file), upload back, byte for byte the same; a plain file to DIS/FIX 128 and back; a file not there; a bad name;
  - leaving with FCTN-= from a session, Q from the session menu and FCTN-= from the address book, after 80 columns with colours: the title screen identical, pixel by pixel, to the one at power-up;
  - the baseline of capitals, digits, lower case and accented capitals;
  - the Italian ROM; the firmware of `main` (the ROM says it lacks the commands).

  `ROM/screenshots.py` makes `docs/screenshots/`.

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
