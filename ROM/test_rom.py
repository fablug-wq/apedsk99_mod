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
ROM = os.path.join(HERE, "TINETC.bin")
HOST = "127.0.0.1:%d" % tc.BBS_PORT


def rows(m):
    return [r.rstrip() for r in m.screen_text()]


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
        wait_for(m, "RUBRICA", 300)
        return m

    def connect(self, m):
        m.type(HOST + "\r")
        wait_for(m, "READY")

    def test_book_screen(self):
        with self.machine() as m:
            r = rows(m)
            self.assertEqual(r[0].strip(), "TI-NET TERM 0.1")
            self.assertIn("OPPURE SCRIVI HOST[:PORTA]", r[13])
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
            wait_for(m, "R=RIAGGANCIA")
            m.type("R")
            wait_for(m, "RUBRICA")

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
            wait_for(m, "Chiusa dalla BBS")
            m.type(" ")
            wait_for(m, "RUBRICA")

    def test_connection_refused(self):
        with self.machine() as m:
            m.type("127.0.0.1:1\r")
            wait_for(m, "Connessione non riuscita")

    def test_address_book(self):
        with self.machine() as m:
            m.type(HOST)
            m.press("FCTN", "8")
            wait_for(m, "NOME:")
            m.type("Finta\r")
            wait_for(m, "Salvato in DSK1.BBSLIST")
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
            m.type("R")
            wait_for(m, "RUBRICA")
            m.press("FCTN", "3")
            wait_for(m, "Cancello quale")
            m.type("1")
            wait_for(m, "Voce cancellata")
            self.assertEqual(rows(m)[4], "")

    def test_options(self):
        with self.machine() as m:
            m.press("FCTN", "9")
            wait_for(m, "OPZIONI")
            self.assertIn("BIANCO SU BLU", rows(m)[3])
            self.assertIn("SI", rows(m)[4])
            m.type("1")
            self.assertIn("VERDE SU NERO", rows(m)[3])
            self.assertEqual(m.vregs()[7], 0x31)
            m.type("2")
            self.assertIn("NO", rows(m)[4])
            m.press("FCTN", "9")
            wait_for(m, "RUBRICA")
            self.connect(m)
            self.assertEqual(rows(m)[3], "NAWS 40x24")
            self.assertNotIn("F9 MENU", rows(m)[23])
        with self.machine() as m:                                       # kept in DSK1.BBSLIST
            self.assertEqual(m.vregs()[7], 0x31)

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
                wait_for(m, "non ha i comandi", 300)


if __name__ == "__main__":
    unittest.main()
