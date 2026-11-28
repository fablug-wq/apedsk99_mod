"""
APEDSK TERMINAL tests: the cartridge on the real console ROM and GROM (ti99-headless),
APEDSK99 as a co-simulated card (the real DSR and firmware, harness/cosim), the
fake telnet BBS (harness/fake_bbs.py).

    TI99HEADLESS=/path/to/ti99-headless XDT99=/path/to/xdt99 python3 ROM/test_rom.py -v
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "harness", "cosim"))
import test_cosim as tc                                     # noqa: E402

th = tc.th
ROM = os.path.join(HERE, "APETERM8.bin")                    # English, 32K banked
ROM_IT = os.path.join(tempfile.gettempdir(), "APETERMI8-test.bin")   # Italian, built for the test
HOST = "127.0.0.1:%d" % tc.BBS_PORT


def rows(m):
    return [r.rstrip() for r in m.screen_text()]


sys.path.insert(0, HERE)
import font64                                               # noqa: E402
import inverse                                              # noqa: E402
sys.path.insert(0, os.path.join(REPO, "harness"))
import fake_bbs                                             # noqa: E402,F811
_NIB, _NIBI = {}, {}
for _code, _g in enumerate(font64.table()):
    if 32 <= _code < 127 or _code >= 176:
        _NIB.setdefault(tuple(b >> 4 for b in _g), _code)
        _NIBI.setdefault(tuple(15 - (b >> 4) for b in _g), _code)


def inverse64(m, r):
    """row r of the 64-column screen: the characters drawn in inverse, '.' elsewhere"""
    pat = m.vram(r * 256, 256)
    out = ""
    for c in range(64):
        base = (c >> 1) * 8
        cell = tuple((pat[base + y] >> (0 if c & 1 else 4)) & 15 for y in range(8))
        code = _NIBI.get(cell)
        out += chr(code) if code is not None and code < 127 and cell != (15,) * 8 else "."
    return out


def rows80(m):
    """the 80-column screen of the F18A: 30 rows of names at >0000"""
    v = m.vram(0, 2400)
    return ["".join(chr(b) if 32 <= b < 127 else "\u00b7" for b in v[r * 80:r * 80 + 80]).rstrip()
            for r in range(30)]


def attr80(m, r, c):
    return m.vram(0x2800 + r * 80 + c, 1)[0]


def wait80(m, text, max_frames=900, step=10):
    for _ in range(max_frames // step):
        if any(text in r for r in rows80(m)):
            return
        m.frames(step)
    raise AssertionError("%r not on the 80-column screen: %s" % (text, [r for r in rows80(m) if r]))


def rows64(m):
    """the 64-column bitmap screen as text: each 4 x 8 cell matched against the font"""
    pat = m.vram(0, 0x1800)
    out = []
    for r in range(24):
        line = []
        for c in range(64):
            base = r * 256 + (c >> 1) * 8
            cell = tuple((pat[base + y] >> (0 if c & 1 else 4)) & 15 for y in range(8))
            code = _NIB.get(cell)
            line.append("?" if code is None else (chr(code) if code < 127 else "\u00b7"))
        out.append("".join(line).rstrip())
    return out


def wait64(m, text, max_frames=900, step=10):
    for _ in range(max_frames // step):
        if any(text in r for r in rows64(m)):
            return
        m.frames(step)
    raise AssertionError("%r not on the 64-column screen: %s" % (text, [r for r in rows64(m) if r]))


def wait_for(m, text, max_frames=900, step=10):
    for _ in range(max_frames // step):
        if any(text in r for r in rows(m)):
            return
        m.frames(step)
    raise AssertionError("%r not on the screen: %s" % (text, [r for r in rows(m) if r]))


def to_book(m):
    """FCTN-9 from the options: wait for the address book itself (the options
    footer also says ADDRESS BOOK)"""
    m.press("FCTN", "9")
    wait_for(m, "OR TYPE HOST")


def disk1(rig):
    with open(os.path.join(rig.sd, "DISKS", "_APEDSK1.DSK"), "rb") as f:
        return f.read()


@unittest.skipUnless(tc.AVAILABLE, "ti99-headless with external cards not found (TI99HEADLESS)")
class TestRom(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.check_call([os.path.join(REPO, "harness", "cosim", "build.sh"), tc.SERVER])
        subprocess.check_call([os.path.join(HERE, "build.sh")])
        subprocess.check_call([os.path.join(HERE, "build.sh"), "it", ROM_IT])

    def setUp(self):
        self.rig = tc.Rig()

    def tearDown(self):
        self.rig.close()

    def machine(self, card=None, vdp="TMS9918A"):
        m = th.Machine(ROM, disk="NONE", cards=[card or self.rig.card()], vdp=vdp)
        m.menu(2)
        wait_for(m, "ADDRESS BOOK", 300)
        return m

    def connect(self, m):
        m.type(HOST + "\r")
        wait_for(m, "READY")

    def test_book_screen(self):
        with self.machine() as m:
            r = rows(m)
            self.assertEqual(r[0][:20], " APEDSK TERMINAL 1.0")
            self.assertIn("F= QUIT", r[0])
            self.assertEqual(r[4], "")                                 # nothing read from disk
            def rows_of(code):                                         # the rows a pattern uses
                p = m.vram(0x800 + code * 8, 8)
                return [y for y in range(8) if p[y]]
            for c in "HAx1.":                                          # one baseline: row 6
                self.assertEqual(max(rows_of(ord(c))), 6, c)
            self.assertEqual(max(rows_of(ord("g"))), 7)                # a descender below it
            for code in (142, 144, 153, 165):                          # accented capitals
                self.assertEqual(max(rows_of(code)), 6, code)
            self.assertIn("OR TYPE HOST[:PORT]", r[13])
            self.assertEqual(m.vregs()[1] & 0x18, 0x10)                 # text mode
            m.type("abc{LEFT}")                                       # FCTN-S deletes
            self.assertIn(">ab", rows(m)[14])
            self.assertEqual(m.vregs()[1] & 0x18, 0x10)                # still text mode after KSCAN

    def test_session(self):
        with self.machine() as m:
            self.connect(m)
            r = rows(m)
            self.assertEqual(r[0], "FAKE BBS")                        # ESC[2J ESC[H: cleared, at home
            self.assertEqual(r[1], "NEGO DO-1 DO-3 WILL-24 WILL-31")
            self.assertEqual(r[2], "TTYPE ANSI")
            self.assertEqual(r[3], "NAWS 40x23")
            self.assertEqual(m.vram(4 * 40, 4), bytes([0xC9, 0xCD, 0xCD, 0xBB]))   # CP437 as is
            self.assertEqual(m.vram(5 * 40, 6), b"IAC>\xff<")            # IAC IAC -> >FF
            self.assertTrue(r[23].startswith("·" + HOST) or HOST in r[23])
            self.assertIn("ANSI 40x23", r[23])
            self.assertIn("F9 MENU", r[23])
            m.type("Hello\r")
            wait_for(m, "Hello")
            self.assertNotIn("HelloHello", "\n".join(rows(m)))         # the BBS echoes, we do not

            # the ANSI test page
            m.type("ANSI\r")
            wait_for(m, "ANSI DONE")
            r = rows(m)
            self.assertEqual(r[0], "ANSI TEST")
            self.assertEqual(r[4][9:11], "XX")
            self.assertEqual(r[9], "LINEA")                            # ESC[K from column 6
            self.assertEqual(r[2][29:34], "ROSSO")                     # SGR read and ignored
            self.assertEqual(r[13][:11], "CPR ^[12;3R")                # ESC[6n answered
            self.assertEqual(r[19][19], "Z")
            self.assertEqual(r[13][11], "U")                           # ESC[s ... ESC[u
            self.assertEqual(m.vram(15 * 40, 5), bytes([0xC9, 0xCD, 0xCD, 0xCD, 0xBB]))

            # what the keys send
            m.type("KEYS\r")
            wait_for(m, "KEYS: Q")
            m.press("CTRL", "C")
            m.press("FCTN", "E")
            m.press("FCTN", "7")
            m.press("FCTN", "S")
            m.press("FCTN", "1")
            m.press("ENTER")
            m.type("Q")
            wait_for(m, "KEYS DONE")
            text = "\n".join(rows(m))
            self.assertIn("03 1B 5B 41 1B 08 7F 0D", text)

            # FCTN-9, R: hang up, back to the address book
            m.press("FCTN", "9")
            wait_for(m, "H=HANG UP")
            m.type("H")
            wait_for(m, "ADDRESS BOOK")

    def test_local_echo(self):
        """AUTO: local echo while the server does not echo (WONT ECHO), off again after WILL ECHO"""
        with self.machine() as m:
            self.connect(m)
            m.type("NOECHO\r")
            wait_for(m, "NOECHO ON")
            m.type("AB\r")
            wait_for(m, "GOT 41 42 0D")
            self.assertIn("AB", rows(m))                               # our own echo
            m.type("ECHO\r")
            tc.wait_line(m, "ECHO ON")
            m.type("CD\r")
            tc.wait_line(m, "CD")
            self.assertNotIn("CDCD", "\n".join(rows(m)))

    def test_plain_service(self):
        """a service that is not a BBS (no telnet, no echo), ENTER = CR LF, echo off"""
        with self.machine() as m:
            m.press("FCTN", "9")
            wait_for(m, "OPTIONS")
            m.type("4")
            self.assertIn("CR LF", rows(m)[6])
            to_book(m)
            m.type("127.0.0.1:%d\r" % tc.RAW_PORT)
            wait_for(m, "RAW READY")
            m.type("HI\r")
            wait_for(m, "GOT 48 49 0D 0A")
            self.assertIn("HI", rows(m))                               # AUTO: local echo
            m.press("FCTN", "9")
            m.type("H")
            wait_for(m, "ADDRESS BOOK")
            m.press("FCTN", "9")
            wait_for(m, "OPTIONS")
            m.type("33")                                               # AUTO -> SI -> NO
            self.assertIn("NO", rows(m)[5])
            to_book(m)
            m.type("127.0.0.1:%d\r" % tc.RAW_PORT)
            wait_for(m, "RAW READY")
            m.type("XY\r")
            wait_for(m, "GOT 58 59 0D 0A")
            self.assertNotIn("XY", rows(m))
        self.assertNotIn(b"APENET", disk1(self.rig))                  # nothing written unasked

    def test_64_columns(self):
        """bitmap mode, 64 x 23 for the BBS, the same ANSI handling; back to text mode after"""
        with self.machine() as m:
            m.press("FCTN", "9")
            wait_for(m, "OPTIONS")
            m.type("5")
            self.assertIn("64", rows(m)[7])
            to_book(m)
            m.type(HOST + "\r")
            wait64(m, "READY")
            v = m.vregs()
            self.assertEqual((v[0] & 2, v[1] & 0x18, v[3], v[4]), (2, 0, 0x9F, 0x03))   # bitmap
            r = rows64(m)
            self.assertEqual(r[0], "FAKE BBS")
            self.assertEqual(r[3], "NAWS 64x23")
            self.assertIn("ANSI 64x23", r[23])
            self.assertIn("F9 MENU", r[23])
            self.assertEqual(r[4][:4], "\u00b7" * 4)                   # CP437 box corner, lines
            m.type("Hello\r")
            wait64(m, "Hello")
            m.type("ANSI\r")
            wait64(m, "ANSI DONE")
            r = rows64(m)
            self.assertEqual(r[0], "ANSI TEST")
            self.assertEqual(r[4][9:11], "XX")
            self.assertEqual(r[9], "LINEA")
            self.assertEqual(r[13][:11], "CPR ^[12;3R")
            self.assertEqual(r[19][19], "Z")
            self.assertEqual(r[13][11], "U")
            m.type("COLORS\r")                                         # inverse: the cell XOR
            wait64(m, "COLORS DONE")
            r = rows64(m)
            i = next(n for n, t in enumerate(r) if t == "COLORS")
            self.assertEqual(inverse64(m, i + 1)[:8], ".Hi.A1..")    # the space is a full block
            self.assertEqual(r[i + 1][0], "a")
            self.assertEqual(r[i + 1][7], "b")
            m.type("BIG\r")                                            # scrolling
            wait64(m, "END", 6000)
            self.assertIn("ANSI 64x23", rows64(m)[23])
            m.press("FCTN", "9")
            wait64(m, "H=HANG UP")
            m.type("H")
            wait_for(m, "ADDRESS BOOK")
            self.assertEqual(m.vregs()[1] & 0x18, 0x10)                 # text mode again

    def test_bulk(self):
        with self.machine() as m:
            self.connect(m)
            m.type("BIG\r")
            wait_for(m, "END", 3000)
            self.assertIn("ANSI 40x23", rows(m)[23])                   # the status row survived

    def test_bbs_hangs_up(self):
        with self.machine() as m:
            self.connect(m)
            m.type("QUIT\r")
            wait_for(m, "Closed by the BBS")
            m.type(" ")
            wait_for(m, "ADDRESS BOOK")

    def test_connection_refused(self):
        with self.machine() as m:
            m.type("127.0.0.1:1\r")
            wait_for(m, "Connection failed")

    def save_file(self, m, name=None):
        """FCTN-6 in the address book, the name (DSK1.APENET if None), ENTER"""
        m.press("FCTN", "6")
        wait_for(m, "SAVE: DSK1.")
        if name:
            for _ in range(20):
                m.press("FCTN", "S")
            m.type(name)
        m.type("\r")
        wait_for(m, "Saved.")

    def load_file(self, m):
        m.press("FCTN", "5")
        wait_for(m, "LOAD: DSK1.APENET")
        m.type("\r")
        wait_for(m, "Loaded.")

    def test_address_book(self):
        """entries are added and deleted in memory; LOAD and SAVE ask the file name"""
        with self.machine() as m:
            m.type(HOST)
            m.press("FCTN", "8")
            wait_for(m, "NAME:")
            m.type("Finta\r")
            wait_for(m, "Added. F6 saves")
            self.assertEqual(rows(m)[4][1:8], "1 Finta")
            self.assertIn(HOST, rows(m)[4])
            self.assertNotIn(b"APENET", disk1(self.rig))
            m.press("FCTN", "6")                                       # FCTN-9: nothing written
            wait_for(m, "SAVE: DSK1.APENET")
            m.press("FCTN", "9")
            m.frames(60)
            self.assertNotIn(b"APENET", disk1(self.rig))
            self.save_file(m)
        img = disk1(self.rig)
        self.assertIn(b"Finta|" + HOST.encode(), img)
        self.assertIn(b"#P0S1E0N0C0A1", img)
        with self.machine() as m:                                       # not read at start
            self.assertEqual(rows(m)[4], "")
            self.load_file(m)
            self.assertEqual(rows(m)[4][1:8], "1 Finta")
            m.press("FCTN", "X")
            self.assertIn(">" + HOST, rows(m)[14])
            m.type("\r")
            wait_for(m, "READY")
            m.press("FCTN", "9")
            m.type("H")
            wait_for(m, "ADDRESS BOOK")
            m.press("FCTN", "3")
            wait_for(m, "Delete which")
            m.type("1")
            wait_for(m, "Entry deleted")
            self.assertEqual(rows(m)[4], "")
        with self.machine() as m:                                       # not saved: still there
            self.load_file(m)
            self.assertEqual(rows(m)[4][1:8], "1 Finta")
            m.press("FCTN", "5")                                       # another file: an error
            wait_for(m, "LOAD: DSK1.APENET")
            m.press("FCTN", "S")
            m.press("FCTN", "S")
            m.type("X\r")
            wait_for(m, "Disk error.")
            self.assertEqual(rows(m)[4][1:8], "1 Finta")               # nothing lost
            m.press("FCTN", "5")
            wait_for(m, "LOAD: DSK1.APENX")                           # the last name typed
            m.press("FCTN", "9")

    def test_port(self):
        """a host without a port: PORT: asked (empty: 23), for a call and for an entry"""
        with self.machine() as m:
            m.type("127.0.0.1\r")
            wait_for(m, "PORT:")
            self.assertIn("(default=23)", rows(m)[16])
            m.type("%d\r" % tc.BBS_PORT)
            wait_for(m, "READY")
            m.press("FCTN", "9")
            m.type("H")
            wait_for(m, "ADDRESS BOOK")
            m.type("127.0.0.1")
            m.press("FCTN", "8")
            wait_for(m, "PORT:")
            m.type("\r")                                               # empty: 23
            wait_for(m, "NAME:")
            self.assertIn(">127.0.0.1:23", rows(m)[14])
            m.type("Telnet\r")
            wait_for(m, "Added")
            self.assertIn("127.0.0.1:23", rows(m)[4])
            m.type("127.0.0.1\r")                                      # FCTN-9: not called
            wait_for(m, "PORT:")
            m.press("FCTN", "9")
            m.frames(30)
            self.assertNotIn("Connecting", "\n".join(rows(m)))

    def test_options(self):
        """options last for the session, SAVE keeps them with the address book"""
        with self.machine() as m:
            m.press("FCTN", "9")
            wait_for(m, "OPTIONS")
            self.assertIn("WHITE ON BLUE", rows(m)[3])
            self.assertIn("YES", rows(m)[4])
            self.assertIn("No F18A", rows(m)[10])
            m.type("1")
            self.assertIn("GREEN ON BLACK", rows(m)[3])
            self.assertEqual(m.vregs()[7], 0x31)
            m.type("2")
            self.assertIn("NO", rows(m)[4])
            m.type("55")                                               # 40 -> 64 -> 40: no 80
            self.assertIn("40", rows(m)[7])
            m.type("6")
            self.assertIn("NO", rows(m)[8])
            to_book(m)
            self.connect(m)
            self.assertEqual(rows(m)[3], "NAWS 40x24")
            self.assertNotIn("F9 MENU", rows(m)[23])
            m.press("FCTN", "9")
            m.type("H")
            wait_for(m, "ADDRESS BOOK")
            self.assertEqual(rows(m)[23][:10], " F3 DELETE")             # the menu row went
        with self.machine() as m:                                       # not saved: defaults
            self.assertEqual(m.vregs()[7], 0xF4)
            m.press("FCTN", "9")
            wait_for(m, "OPTIONS")
            m.type("1")
            to_book(m)
            self.save_file(m)
        self.assertIn(b"#P1S1E0N0C0A1", disk1(self.rig))
        with self.machine() as m:
            self.assertEqual(m.vregs()[7], 0xF4)
            self.load_file(m)
            self.assertEqual(m.vregs()[7], 0x31)

    def test_inverse_40(self):
        """SGR 7 in 40 columns: the inverse characters of inverse.py"""
        with self.machine() as m:
            self.connect(m)
            m.type("COLORS\r")
            wait_for(m, "COLORS DONE")
            r = rows(m)
            i = r.index("COLORS")
            line = m.vram((i + 1) * 40, 8)
            inv = inverse.inverse_map()
            self.assertEqual(line, b"a" + bytes(inv[ord(c) - 32] for c in "Hi A1.") + b"b")
            self.assertEqual(inv[ord("i") - 32], inv[ord("I") - 32])     # lower case: the capital
            for c in "H1. ":
                code = inv[ord(c) - 32]
                self.assertEqual(m.vram(0x800 + code * 8, 8),
                                 bytes(255 - b for b in m.vram(0x800 + ord(c) * 8, 8)))
            self.assertEqual(m.vram((i + 2) * 40, 3), b"RGN")             # colours: ignored

    def test_80_columns(self):
        """F18A: 80 x 25, a colour byte per position, ANSI colours and inverse"""
        with self.machine(vdp="F18A") as m:
            m.press("FCTN", "9")
            wait_for(m, "OPTIONS")
            self.assertIn("F18A: 80 columns", rows(m)[10])
            m.type("55")
            self.assertIn("80", rows(m)[7])
            to_book(m)
            m.type(HOST + "\r")
            wait80(m, "READY")
            v = m.vregs()
            self.assertEqual((v[0] & 4, v[1] & 0x18), (4, 0x10))       # 80-column text mode
            r = rows80(m)
            self.assertEqual(r[0], "FAKE BBS")
            self.assertEqual(r[3], "NAWS 80x25")
            self.assertIn("ANSI 80x25", r[25])
            self.assertIn("F9 MENU", r[25])
            self.assertEqual(attr80(m, 0, 0), 0xB0)                    # bold yellow (SGR 1;33)
            self.assertEqual(attr80(m, 3, 0), 0x70)                    # light grey on black
            m.type("COLORS\r")
            wait80(m, "COLORS DONE")
            r = rows80(m)
            i = r.index("COLORS")
            self.assertEqual(r[i + 1][:8], "aHi A1.b")
            self.assertEqual([attr80(m, i + 1, c) for c in (0, 1, 7)], [0x70, 0x07, 0x70])
            self.assertEqual([attr80(m, i + 2, c) for c in range(3)], [0x10, 0xA0, 0x70])
            self.assertEqual([attr80(m, i + 3, c) for c in range(2)], [0x34, 0x43])
            m.type("ANSI\r")
            wait80(m, "ANSI DONE")
            r = rows80(m)
            self.assertEqual(r[4][9:11], "XX")
            self.assertEqual(r[13][:11], "CPR ^[12;3R")
            m.type("BIG\r")
            wait80(m, "END", 6000)
            self.assertIn("ANSI 80x25", rows80(m)[25])
            m.press("FCTN", "9")
            wait80(m, "H=HANG UP")
            m.type("H")
            wait_for(m, "ADDRESS BOOK")
            v = m.vregs()
            self.assertEqual((v[0] & 4, v[1] & 0x18), (0, 0x10))       # 40 columns again
            m.press("FCTN", "9")                                       # two colours
            wait_for(m, "OPTIONS")
            m.type("6")
            to_book(m)
            m.type(HOST + "\r")
            wait80(m, "READY")
            self.assertEqual(attr80(m, 0, 0), 0xF4)                    # the palette, no colour
            m.type("COLORS\r")
            wait80(m, "COLORS DONE")
            i = rows80(m).index("COLORS")
            self.assertEqual([attr80(m, i + 1, c) for c in (0, 1)], [0xF4, 0x4F])

    def xfer(self, m, cmd, key, name, wait="Done."):
        """the BBS command, then F9 D / U and the file name"""
        m.type(cmd + "\r")
        tc.wait_line(m, cmd)
        m.press("FCTN", "9")
        wait_for(m, "D=DOWNLOAD")
        m.type(key)
        wait_for(m, "DSK1.")
        for _ in range(16):
            m.press("FCTN", "S")
        m.type(name + "\r")
        wait_for(m, wait, 6000)
        m.type(" ")

    def test_xmodem(self):
        """download TIFILES (128 and 1K blocks) and a plain file, upload them back"""
        prog = fake_bbs.test_program()
        recv = os.path.join(self.rig.dir, "xrecv.bin")
        with self.machine() as m:
            self.connect(m)
            self.xfer(m, "XSEND", "D", "DSK1.TEST")
            wait_for(m, "XSEND OK")
            self.xfer(m, "XRECV", "U", "DSK1.TEST")
            wait_for(m, "XRECV OK 896")
            with open(recv, "rb") as f:
                self.assertEqual(f.read(), prog)                        # the same file back
            # again, 1K blocks: the file is there, replace it
            m.type("XSEND1K\r")
            tc.wait_line(m, "XSEND1K")
            m.press("FCTN", "9")
            wait_for(m, "D=DOWNLOAD")
            m.type("D")
            wait_for(m, "DSK1.TEST")
            m.type("\r")
            wait_for(m, "Replace it? Y/N")
            m.type("Y")
            wait_for(m, "Done.", 6000)
            m.type(" ")
            wait_for(m, "XSEND OK")
            os.remove(recv)
            self.xfer(m, "XRECV", "U", "DSK1.TEST")
            wait_for(m, "XRECV OK 896")
            with open(recv, "rb") as f:
                self.assertEqual(f.read(), prog)
            # a file that is not a TI file: DIS/FIX 128
            self.xfer(m, "XSENDTXT", "D", "DSK1.TEXT")
            wait_for(m, "XSEND OK")
            self.xfer(m, "XRECV", "U", "DSK1.TEXT")
            wait_for(m, "XRECV OK 640")
            with open(recv, "rb") as f:
                got = f.read()
            self.assertEqual(got[:16], bytes([7]) + b"TIFILES" + bytes([0, 2, 0, 2, 0, 128, 3, 0]))
            self.assertEqual(got[128:128 + 384], fake_bbs.TEXT_FILE.ljust(384, b"\x1a"))
            # a name that is not DSKn.NAME, a file that is not there
            m.press("FCTN", "9")
            wait_for(m, "D=DOWNLOAD")
            m.type("U")
            wait_for(m, "DSK1.")
            for _ in range(16):
                m.press("FCTN", "S")
            m.type("DSK1.NONE\r")
            wait_for(m, "File not found.")
            m.type(" ")
            m.press("FCTN", "9")
            wait_for(m, "D=DOWNLOAD")
            m.type("U")
            wait_for(m, "DSK1.")
            for _ in range(16):
                m.press("FCTN", "S")
            m.type("FOO\r")
            wait_for(m, "DSKn.NAME")
            m.type(" ")
            m.type("QUIT\r")
            wait_for(m, "Closed by the BBS")

    def test_quit(self):
        """FCTN-= in a session, Q in the session menu, FCTN-= in the address book: after
        80 columns with colours on the F18A, the title screen exactly as at power-up"""
        with th.Machine(ROM, disk="NONE", cards=[self.rig.card()], vdp="F18A") as m:
            m.frames(120)
            title = m.screenshot()
            for how in ("FCTN-=", "Q", "book"):
                m.menu(2)
                wait_for(m, "ADDRESS BOOK", 300)
                m.press("FCTN", "9")
                wait_for(m, "OPTIONS")
                m.type("55")
                to_book(m)
                m.type(HOST + "\r")
                wait80(m, "READY")
                if how == "FCTN-=":
                    m.press("FCTN", "=")
                elif how == "Q":
                    m.press("FCTN", "9")
                    wait80(m, "Q=QUIT")
                    m.type("Q")
                else:
                    m.press("FCTN", "9")
                    wait80(m, "H=HANG UP")
                    m.type("H")
                    wait_for(m, "ADDRESS BOOK")
                    m.press("FCTN", "=")
                m.frames(120)
                self.assertEqual(m.screenshot(), title, how)

    def test_italian(self):
        """the Italian ROM (-D ITALIAN): same code, other texts, H hangs up as in English"""
        with th.Machine(ROM_IT, disk="NONE", cards=[self.rig.card()]) as m:
            m.menu(2)
            wait_for(m, "RUBRICA", 300)
            self.assertIn("OPPURE SCRIVI HOST[:PORTA]", rows(m)[13])
            m.type("127.0.0.1")
            m.press("FCTN", "8")
            wait_for(m, "PORTA:")
            m.type("%d\r" % tc.BBS_PORT)
            wait_for(m, "NOME:")
            m.type("Finta\r")
            wait_for(m, "Aggiunta")
            m.press("FCTN", "6")
            wait_for(m, "FILE: DSK1.APENET")
            m.type("\r")
            wait_for(m, "Salvato.")
            m.press("FCTN", "X")
            m.type("\r")
            wait_for(m, "READY")
            m.press("FCTN", "9")
            wait_for(m, "H=RIAGGANCIA")
            m.type("H")
            wait_for(m, "RUBRICA")

    def test_old_firmware(self):
        """the firmware of main (no terminal commands): the ROM says so"""
        with tempfile.TemporaryDirectory() as d:
            sk = os.path.join(d, "APEDSK99_012s")
            arch = subprocess.run(["git", "-C", REPO, "archive", "8878dec", "Arduino/APEDSK99_012s"],
                                  capture_output=True)
            if arch.returncode:
                self.skipTest("git archive 8878dec failed")
            subprocess.run(["tar", "-x", "-C", d], input=arch.stdout, check=True)
            os.rename(os.path.join(d, "Arduino", "APEDSK99_012s"), sk)
            server = os.path.join(d, "firmware_server")
            subprocess.check_call([os.path.join(REPO, "harness", "cosim", "build.sh"), server, sk])
            path, opts = self.rig.card()
            opts = dict(opts, server=server)
            with th.Machine(ROM, disk="NONE", cards=[(path, opts)]) as m:
                m.menu(2)
                wait_for(m, "has no terminal", 300)


if __name__ == "__main__":
    unittest.main()
