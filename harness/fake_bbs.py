#!/usr/bin/env python3
"""Fake telnet BBS for the harness.

On connect it negotiates like a real BBS (WILL ECHO, WILL SGA, DO TTYPE, DO NAWS),
asks the terminal type, then sends an ANSI banner reporting what it understood.
Then it works in character mode, echoing what it receives. Lines:
  BIG   -> sends 5000 bytes of a known pattern (includes IAC escaped as IAC IAC)
  ANSI  -> an ANSI test page: cursor positioning, erase, colours, save/restore,
           a cursor position request (ESC[6n) whose answer it prints back
  KEYS  -> shows the code of every byte received (hex) until Q
  NOECHO -> says WONT ECHO and stops echoing: every line comes back as
           "GOT <hex bytes>" (CR, and LF if it follows), until the line ECHO
  QUIT  -> says goodbye and closes the connection

With "raw" as third argument it is a plain TCP service instead (as POP3 or
SMTP would be): no telnet negotiation, no echo, "RAW READY", then lines come
back as "GOT <hex>"; QUIT closes.

usage: fake_bbs.py [port] [address] [raw]   (default 2323 on 127.0.0.1;
       use address 0.0.0.0 to reach it from the TI over the LAN)
"""
import re, socket, sys, time

IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240
ECHO, SGA, TTYPE, NAWS = 1, 3, 24, 31


def big_pattern():
    return bytes((i * 7) % 256 for i in range(5000))


def lines_back(conn, stop):
    """every line received -> GOT <hex of its bytes, CR and a following LF included>"""
    conn.settimeout(30)
    line, pending = b'', b''
    while True:
        c, pending = (pending, b'') if pending else (conn.recv(1), b'')
        if not c:
            return False
        line += c
        if c == b'\r':
            conn.settimeout(0.3)
            try:
                nxt = conn.recv(1)
                if nxt == b'\n':
                    line += nxt
                else:
                    pending = nxt                     # the start of the next line
            except socket.timeout:
                pass
            conn.settimeout(30)
            text = line.strip(b'\r\n\x00')
            conn.sendall(b'GOT ' + b' '.join(b'%02X' % x for x in line) + b'\r\n')
            if text.upper() == stop:
                return True
            line = b''


def handle_raw(conn):
    conn.sendall(b'RAW READY\r\n')
    lines_back(conn, b'QUIT')


def handle(conn):
    conn.settimeout(3)
    conn.sendall(bytes([IAC, WILL, ECHO, IAC, WILL, SGA, IAC, DO, TTYPE, IAC, DO, NAWS]))
    ttype, naws, opts, data = None, None, [], b''
    buf = b''
    deadline = time.time() + 3
    def answered(opt, value):                       # WONT, or WILL and then the value
        return value is not None or (WONT, opt) in opts
    while time.time() < deadline and not (answered(TTYPE, ttype) and answered(NAWS, naws)):
        try:
            chunk = conn.recv(256)
        except socket.timeout:
            break
        if not chunk:
            return
        buf += chunk
        while True:                                   # parse what we have
            i = buf.find(bytes([IAC]))
            if i < 0 or i + 1 >= len(buf):
                break
            cmd = buf[i + 1]
            if cmd in (DO, DONT, WILL, WONT):
                if i + 2 >= len(buf):
                    break
                opt = buf[i + 2]
                opts.append((cmd, opt))
                if cmd == WILL and opt == TTYPE:
                    conn.sendall(bytes([IAC, SB, TTYPE, 1, IAC, SE]))     # SEND
                buf = buf[i + 3:]
            elif cmd == SB:
                j = buf.find(bytes([IAC, SE]), i)
                if j < 0:
                    break
                sub = buf[i + 2:j]
                if sub[0] == TTYPE and sub[1] == 0:
                    ttype = sub[2:].decode('ascii', 'replace')
                elif sub[0] == NAWS and len(sub) == 5:
                    naws = (sub[1] * 256 + sub[2], sub[3] * 256 + sub[4])
                buf = buf[j + 2:]
            else:
                buf = buf[i + 2:]
    names = {DO: 'DO', DONT: 'DONT', WILL: 'WILL', WONT: 'WONT'}
    nego = ' '.join('%s-%d' % (names[c], o) for c, o in opts)
    cols = '%dx%d' % naws if naws else 'none'
    banner = ('\x1b[2J\x1b[1;1H\x1b[1;33mFAKE BBS\x1b[0m\r\n'
              'NEGO %s\r\nTTYPE %s\r\nNAWS %s\r\n' % (nego, ttype, cols)).encode()
    banner += bytes([0xC9, 0xCD, 0xCD, 0xBB]) + b'\r\n'          # CP437 box corner + lines
    banner += b'IAC>' + bytes([IAC, IAC]) + b'<\r\n'               # a real 0xFF data byte
    banner += b'READY\r\n'
    conn.sendall(banner)
    print('fake_bbs: nego=%r ttype=%r naws=%r' % (nego, ttype, cols), flush=True)

    conn.settimeout(30)
    line = b''
    while True:
        try:
            chunk = conn.recv(256)
        except socket.timeout:
            return
        if not chunk:
            return
        chunk = re.sub(rb'\xff[\xfb-\xfe].', b'', chunk)  # option answers are not text
        conn.sendall(chunk.replace(b'\r', b'\r\n'))  # echo (we said WILL ECHO)
        line += chunk
        while b'\r' in line:
            cmd, line = line.split(b'\r', 1)
            cmd = cmd.strip().upper()
            if cmd == b'BIG':
                conn.sendall(big_pattern().replace(bytes([IAC]), bytes([IAC, IAC])) + b'END\r\n')
            elif cmd == b'ANSI':
                ansi_page(conn)
            elif cmd == b'KEYS':
                keys(conn)
            elif cmd == b'NOECHO':
                conn.sendall(bytes([IAC, WONT, ECHO]) + b'NOECHO ON\r\n')
                if not lines_back(conn, b'ECHO'):
                    return
                conn.sendall(bytes([IAC, WILL, ECHO]) + b'ECHO ON\r\n')
                line = b''
                conn.settimeout(30)
            elif cmd == b'QUIT':
                conn.sendall(b'Bye\r\n')
                return


def read_until(conn, end, limit=64):
    data = b''
    while not data.endswith(end) and len(data) < limit:
        chunk = conn.recv(1)
        if not chunk:
            break
        data += chunk
    return data


def ansi_page(conn):
    E = '\x1b['
    conn.sendall((E + '2J' + E + 'H' + 'ANSI TEST' +
                  E + '5;10H' + 'XX' +
                  E + '10;1H' + 'LINEA DA TAGLIARE' + E + '10;6H' + E + 'K' +
                  E + '3;30H' + E + '1;31m' + 'ROSSO' + E + '0m' +
                  E + '?25l' + E + '12;3H' + E + '6n').encode())
    cpr = read_until(conn, b'R')
    conn.sendall((E + '14;1H' + 'CPR ' + cpr.decode('ascii', 'replace').replace('\x1b', '^') +
                  E + 's' + E + '20;20H' + 'Z' + E + 'u' + 'U' +
                  E + '16;1H').encode() +
                 bytes([0xC9, 0xCD, 0xCD, 0xCD, 0xBB]) + b'\r\n' +
                 bytes([0xC8, 0xCD, 0xCD, 0xCD, 0xBC]) + b'\r\nANSI DONE\r\n')


def keys(conn):
    conn.sendall(b'KEYS: Q per finire\r\n')
    while True:
        c = conn.recv(1)
        if not c or c == b'Q':
            break
        conn.sendall(b'%02X ' % c[0])
    conn.sendall(b'\r\nKEYS DONE\r\n')


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 2323
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    addr = sys.argv[2] if len(sys.argv) > 2 else '127.0.0.1'
    raw = len(sys.argv) > 3 and sys.argv[3] == 'raw'
    s.bind((addr, port))
    s.listen(1)
    print('fake_bbs: listening on %s:%d' % (addr, port), flush=True)
    while True:
        conn, _ = s.accept()
        try:
            handle_raw(conn) if raw else handle(conn)
        except OSError as e:
            print('fake_bbs:', e, flush=True)
        conn.close()


if __name__ == '__main__':
    main()
