"""
APEDSK99 co-simulation tests: a TI-99/4A in ti99-headless (js99er: console ROM
and GROM, Extended BASIC) with APEDSK99 as a peripheral card whose firmware is
the real sketch (firmware_server), talking to the fake telnet BBS.

    TI99HEADLESS=/path/to/ti99-headless python3 harness/cosim/test_cosim.py -v

Needs ti99-headless 0.2.0 or later (external cards: Machine(cards=...)), set up
(python3 -m ti99headless setup), and a C++ compiler for firmware_server.
"""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
REPO = os.path.dirname(HARNESS)
XDT99 = os.environ.get("XDT99")                      # optional: xdm99 to make the disk images
sys.path.insert(0, os.environ.get("TI99HEADLESS", os.path.join(REPO, "..", "ti99-headless")))
try:
    import ti99headless as th
    AVAILABLE = th.available() and "cards" in th.Machine.__init__.__code__.co_varnames
except ImportError:
    th, AVAILABLE = None, False

BBS_PORT = 2324
RAW_PORT = 2325                                      # the fake BBS as a plain TCP service
SERVER = os.path.join(HERE, "firmware_server")


def blank_dsk(name):
    """a blank 360 KB DSDD-style image (DS/SD 40 tracks, 720 sectors) with a TI volume header"""
    img = bytearray(720 * 256)
    img[0:10] = name.encode().ljust(10)
    img[10:12] = (720).to_bytes(2, "big")
    img[12], img[13:16], img[16], img[17], img[18], img[19] = 9, b"DSK", 0x20, 40, 2, 1
    img[56] = 0x03                                   # sectors 0 and 1 used
    for i in range(56 + 90, 256):
        img[i] = 0xFF                                # no such sectors
    return bytes(img)


class Rig:
    """an SD card folder, an FTP folder, the fake BBS, and the card options"""
    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="cosim-")
        self.sd, self.ftp = os.path.join(self.dir, "sd"), os.path.join(self.dir, "ftp")
        os.makedirs(os.path.join(self.sd, "DISKS"))
        os.makedirs(self.ftp)
        shutil.copy(os.path.join(REPO, "SD", "APEDSK99.DSR"), self.sd)
        with open(os.path.join(self.sd, "CALLerr.txt"), "w") as f:
            f.write("".join(("* error %d" % i).ljust(16) for i in range(16)))
        for n in (1, 2, 3):
            with open(os.path.join(self.sd, "DISKS", "_APEDSK%d.DSK" % n), "wb") as f:
                f.write(blank_dsk("APEDSK%d" % n))
        shutil.copy(os.path.join(REPO, "SD", "DISKS", "NETTEST.DSK"), os.path.join(self.sd, "DISKS"))
        fake = os.path.join(HARNESS, "fake_bbs.py")
        self.bbs = subprocess.Popen([sys.executable, fake, str(BBS_PORT)], cwd=self.dir,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.raw = subprocess.Popen([sys.executable, fake, str(RAW_PORT), "127.0.0.1", "raw"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for port in (BBS_PORT, RAW_PORT):
            for _ in range(50):
                try:
                    socket.create_connection(("127.0.0.1", port), 0.1).close()
                    break
                except OSError:
                    time.sleep(0.05)
        time.sleep(0.1)

    def card(self):
        return (os.path.join(HERE, "apedsk99_card.cjs"),
                {"server": SERVER, "sd": self.sd, "ftp": self.ftp, "log": os.path.join(self.dir, "fw.log")})

    def close(self):
        for p in (self.bbs, self.raw):
            p.kill()
            p.wait()
        shutil.rmtree(self.dir, ignore_errors=True)


def text(m):
    return "\n".join(m.screen_text())


def wait_line(m, line, max_frames=600):
    """run until a screen row is exactly line (spaces aside)"""
    for _ in range(max_frames // 10):
        if any(r.strip() == line for r in m.screen_text()):
            return
        m.frames(10)
    raise AssertionError("no row %r on the screen: %s" % (line, [r for r in m.screen_text() if r.strip()]))


@unittest.skipUnless(AVAILABLE, "ti99-headless with external cards not found (TI99HEADLESS)")
class TestCosim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.check_call([os.path.join(HERE, "build.sh"), SERVER])

    def setUp(self):
        self.rig = Rig()

    def tearDown(self):
        self.rig.close()

    def test_basic_disk(self):
        """TI BASIC SAVE / OLD through the real APEDSK99 DSR and firmware"""
        with th.Machine(disk="NONE", cards=[self.rig.card()]) as m:
            self.assertEqual(m.ram(0x4000, 1), b"\xaa")              # the DSR loaded from the SD card
            m.menu(1)
            m.wait_text("TI BASIC READY", 300)
            m.type('10 PRINT "HELLO APEDSK"\rSAVE DSK1.HI\rNEW\rOLD DSK1.HI\rLIST\r')
            m.frames(60)
            self.assertIn('10 PRINT "HELLO APEDSK"', text(m))
        with open(os.path.join(self.rig.sd, "DISKS", "_APEDSK1.DSK"), "rb") as f:
            img = f.read()
        self.assertIn(b"HI        ", img)                             # its FDR is on the SD card image

    def test_nettest(self):
        """NETTEST (Extended BASIC) against the fake BBS: connect, echo, other commands
        during the session, the BBS hanging up"""
        xb = os.path.join(th.setup_env.js99er_dir(), "src", "assets", "software", "extended_basic.rpk")
        with th.Machine(xb, disk="NONE", cards=[self.rig.card()]) as m:
            m.menu(2)
            m.frames(120)
            m.type('CALL MDSK(1,"NETTEST")\r')
            m.frames(30)
            m.type('RUN "DSK1.NETTEST"\r')
            m.wait_text("HOST", 900)
            m.type("127.0.0.1:%d\r" % BBS_PORT)
            m.wait_text("READY", 3000)
            screen = text(m)
            self.assertIn("  FAKE BBS", screen)                       # ESC[2J ESC[1;1H ESC[1;33m skipped
            self.assertIn("TTYPE None", screen)                       # TTYPE and NAWS refused
            self.assertIn("IAC><", screen)                            # >FF and CP437 dropped
            # typed text comes back as echo (the program reads keys with CALL KEY: hold them)
            m.type("HI\r", hold=12, gap=12, wait=None)
            wait_line(m, "HI")
            # the session survives other network commands: BREAK, CALL TIME, CON
            m.press("FCTN", "4", hold=10, gap=30)
            m.wait_text("BREAKPOINT", 300)
            m.type("CALL TIME\r")
            m.frames(60)
            m.type("CON\r")
            m.frames(60)
            m.type("QUIT\r", hold=12, gap=12, wait=None)
            m.wait_text("CHIUSA DALLA BBS", 3000)
            self.assertIn("Bye", text(m))


if __name__ == "__main__":
    unittest.main()
