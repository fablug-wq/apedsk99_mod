"""Screenshots of TI-NET TERM in the emulator (co-simulated APEDSK99, fake BBS)
-> docs/screenshots/*.png.   TI99HEADLESS=... python3 ROM/screenshots.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_rom as tr                                     # noqa: E402

OUT = os.path.join(tr.REPO, "docs", "screenshots")
os.makedirs(OUT, exist_ok=True)
rig = tr.tc.Rig()
try:
    with tr.th.Machine(tr.ROM, disk="NONE", cards=[rig.card()]) as m:
        m.menu(2)
        tr.wait_for(m, "RUBRICA", 300)
        for name, host in (("Finta locale", tr.HOST), ("Cantina", "cantina.example.org"),
                           ("Retropoint", "retro.example.net:2323")):
            m.type(host)
            m.press("FCTN", "8")
            tr.wait_for(m, "NOME:")
            m.type(name + "\r")
            tr.wait_for(m, "Salvato")
        m.press("FCTN", "X")
        m.screenshot(os.path.join(OUT, "1-rubrica.png"))
        m.type("\r")
        tr.wait_for(m, "READY")
        m.type("Ciao dal TI\r")
        tr.wait_for(m, "Ciao dal TI")
        m.frames(30)
        m.screenshot(os.path.join(OUT, "2-sessione.png"))
        m.type("ANSI\r")
        tr.wait_for(m, "ANSI DONE")
        m.frames(30)
        m.screenshot(os.path.join(OUT, "3-pagina-ansi.png"))
        m.press("FCTN", "9")
        tr.wait_for(m, "R=RIAGGANCIA")
        m.screenshot(os.path.join(OUT, "4-menu-sessione.png"))
        m.type("R")
        tr.wait_for(m, "RUBRICA")
        m.press("FCTN", "9")
        tr.wait_for(m, "OPZIONI")
        m.screenshot(os.path.join(OUT, "5-opzioni.png"))
finally:
    rig.close()
print("\n".join(sorted(os.listdir(OUT))))
