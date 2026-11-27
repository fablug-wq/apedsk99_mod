"""
TI-NET TERM tests: the cartridge on the real console ROM and GROM (ti99-headless),
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
ROM = os.path.join(HERE, "TINET8.bin")                      # English, 16K banked
ROM_IT = os.path.join(HERE, "TINETI8.bin")                 # Italian
HOST = "127.0.0.1:%d" % tc.BBS_PORT


def rows(m):
    return [r.rstrip() for r in m.screen_text()]


sys.path.insert(0, HERE)
import font64                                               # noqa: E402
_NIB = {}
for _code, _g in enumerate(font64.table()):
    if 32 <= _code < 127 or _code >= 176:
        _NIB.setdefault(tuple(b >> 4 for b in _g), _code)


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


@unittest.skipUnless(tc.AVAILABLE, "ti99-headless with external cards not found (TI99HEADLESS)")
class TestRom(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.check_call([os.path.join(REPO, "harness", "cosim", "build.sh"), tc.SERVER])
        subprocess.check_call([os.path.join(HERE, "build.sh")])

    def setUp(self):
        self.rig = tc.Rig()

    def tearDown(self):
        self.rig.close()

    def machine(self, card=None):
        m = th.Machine(ROM, disk="NONE", cards=[card or self.rig.card()])
        m.menu(2)
        wait_for(m, "ADDRESS BOOK", 300)
        return m

    def connect(self, m):
        m.type(HOST + "\r")
        wait_for(m, "READY")

    def test_book_screen(self):
        with self.machine() as m:
            r = rows(m)
            self.assertEqual(r[0].strip(), "TI-NET TERM 0.3")
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
            m.press("FCTN", "9")
            wait_for(m, "ADDRESS BOOK")
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
            m.press("FCTN", "9")
            wait_for(m, "ADDRESS BOOK")
            m.type("127.0.0.1:%d\r" % tc.RAW_PORT)
            wait_for(m, "RAW READY")
            m.type("XY\r")
            wait_for(m, "GOT 58 59 0D 0A")
            self.assertNotIn("XY", rows(m))
        with open(os.path.join(self.rig.sd, "DISKS", "_APEDSK1.DSK"), "rb") as f:
            self.assertIn(b"#P0S1E2N1", f.read())

    def test_64_columns(self):
        """bitmap mode, 64 x 23 for the BBS, the same ANSI handling; back to text mode after"""
        with self.machine() as m:
            m.press("FCTN", "9")
            wait_for(m, "OPTIONS")
            m.type("5")
            self.assertIn("64", rows(m)[7])
            m.press("FCTN", "9")
            wait_for(m, "ADDRESS BOOK")
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
            m.type("BIG\r")                                            # scrolling
            wait64(m, "END", 6000)
            self.assertIn("ANSI 64x23", rows64(m)[23])
            m.press("FCTN", "9")
            wait64(m, "H=HANG UP")
            m.type("H")
            wait_for(m, "ADDRESS BOOK")
            self.assertEqual(m.vregs()[1] & 0x18, 0x10)                 # text mode again
        with open(os.path.join(self.rig.sd, "DISKS", "_APEDSK1.DSK"), "rb") as f:
            self.assertIn(b"#P0S1E0N0C1", f.read())

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

    def test_address_book(self):
        with self.machine() as m:
            m.type(HOST)
            m.press("FCTN", "8")
            wait_for(m, "NAME:")
            m.type("Finta\r")
            wait_for(m, "Saved in DSK1.BBSLIST")
            self.assertEqual(rows(m)[4][1:8], "1 Finta")
            self.assertIn(HOST, rows(m)[4])
        with open(os.path.join(self.rig.sd, "DISKS", "_APEDSK1.DSK"), "rb") as f:
            img = f.read()
        self.assertIn(b"BBSLIST", img)
        self.assertIn(b"Finta|" + HOST.encode(), img)
        self.assertIn(b"#P0S1", img)
        with self.machine() as m:                                       # read back at start
            self.assertEqual(rows(m)[4][1:8], "1 Finta")
            m.press("FCTN", "X")
            self.assertIn(">" + HOST, rows(m)[14])
            self.assertEqual(rows(m)[4][0], ">")
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

    def test_options(self):
        with self.machine() as m:
            m.press("FCTN", "9")
            wait_for(m, "OPTIONS")
            self.assertIn("WHITE ON BLUE", rows(m)[3])
            self.assertIn("YES", rows(m)[4])
            m.type("1")
            self.assertIn("GREEN ON BLACK", rows(m)[3])
            self.assertEqual(m.vregs()[7], 0x31)
            m.type("2")
            self.assertIn("NO", rows(m)[4])
            m.press("FCTN", "9")
            wait_for(m, "ADDRESS BOOK")
            self.connect(m)
            self.assertEqual(rows(m)[3], "NAWS 40x24")
            self.assertNotIn("F9 MENU", rows(m)[23])
        with self.machine() as m:                                       # kept in DSK1.BBSLIST
            self.assertEqual(m.vregs()[7], 0x31)

    def test_italian(self):
        """the Italian ROM (-D ITALIAN): same code, other texts, H hangs up as in English"""
        with th.Machine(ROM_IT, disk="NONE", cards=[self.rig.card()]) as m:
            m.menu(2)
            wait_for(m, "RUBRICA", 300)
            self.assertIn("OPPURE SCRIVI HOST[:PORTA]", rows(m)[13])
            self.connect(m)
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
