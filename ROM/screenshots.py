"""Screenshots of APEDSK TERMINAL in the emulator (F18A, co-simulated APEDSK99,
fake BBS) -> docs/screenshots/*.png.   TI99HEADLESS=... python3 ROM/screenshots.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_rom as tr                                     # noqa: E402

OUT = os.path.join(tr.REPO, "docs", "screenshots")
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    if f.endswith(".png"):
        os.remove(os.path.join(OUT, f))


def shot(m, name):
    m.frames(30)
    m.screenshot(os.path.join(OUT, name))


def columns(m, key_presses):
    m.press("FCTN", "9")
    tr.wait_for(m, "OPTIONS")
    m.type(key_presses)
    return m


def hang_up(m, wait):
    m.press("FCTN", "9")
    wait(m, "H=HANG UP")
    m.type("H")
    tr.wait_for(m, "ADDRESS BOOK")


rig = tr.tc.Rig()
try:
    with tr.th.Machine(tr.ROM, disk="NONE", cards=[rig.card()], vdp="F18A") as m:
        m.menu(2)
        tr.wait_for(m, "ADDRESS BOOK", 300)
        for name, host in (("Local test BBS", tr.HOST), ("Cellar", "cellar.example.org:23"),
                           ("Retropoint", "retro.example.net:2323")):
            m.type(host)
            m.press("FCTN", "8")
            tr.wait_for(m, "NAME:")
            m.type(name + "\r")
            tr.wait_for(m, "Added")
        m.press("FCTN", "6")
        tr.wait_for(m, "SAVE: DSK1.APENET")
        m.type("\r")
        tr.wait_for(m, "Saved")
        m.press("FCTN", "X")
        shot(m, "01-address-book.png")
        m.type("\r")
        tr.wait_for(m, "READY")
        m.type("Hello from the TI\r")
        tr.wait_for(m, "Hello from the TI")
        shot(m, "02-session-40.png")
        m.press("FCTN", "9")
        tr.wait_for(m, "D=DOWNLOAD")
        shot(m, "03-session-menu.png")
        m.type("D")
        tr.wait_for(m, "DSK1.")
        m.type("TEST")
        shot(m, "04-download-name.png")
        m.press("FCTN", "9")
        m.type(" ")
        m.type("XSEND\r")
        tr.tc.wait_line(m, "XSEND")
        m.press("FCTN", "9")
        tr.wait_for(m, "D=DOWNLOAD")
        m.type("D")
        tr.wait_for(m, "DSK1.")
        m.type("TEST\r")
        tr.wait_for(m, "Done.", 6000)
        shot(m, "05-download-done.png")
        m.type(" ")
        hang_up(m, tr.wait_for)
        columns(m, "5")
        shot(m, "06-options.png")
        tr.to_book(m)
        m.press("FCTN", "X")
        m.type("\r")
        tr.wait64(m, "READY")
        m.type("DEMO\r")
        tr.wait64(m, "Your choice")
        shot(m, "07-session-64.png")
        hang_up(m, tr.wait64)
        columns(m, "5")
        tr.to_book(m)
        m.press("FCTN", "X")
        m.type("\r")
        tr.wait80(m, "READY")
        m.type("DEMO\r")
        tr.wait80(m, "Your choice")
        shot(m, "08-session-80-colours.png")
        hang_up(m, tr.wait80)
        columns(m, "6")
        tr.to_book(m)
        m.press("FCTN", "X")
        m.type("\r")
        tr.wait80(m, "READY")
        m.type("DEMO\r")
        tr.wait80(m, "Your choice")
        shot(m, "09-session-80-two-colours.png")
finally:
    rig.close()
print("\n".join(sorted(os.listdir(OUT))))
