#!/usr/bin/env python3
"""Fake telnet BBS for the harness.

On connect it negotiates like a real BBS (WILL ECHO, WILL SGA, DO TTYPE, DO NAWS),
asks the terminal type, then sends an ANSI banner reporting what it understood.
Then it works in character mode, echoing what it receives. Lines:
  BIG   -> sends 5000 bytes of a known pattern (includes IAC escaped as IAC IAC)
  QUIT  -> says goodbye and closes the connection

usage: fake_bbs.py [port] [address]   (default 2323 on 127.0.0.1;
       use address 0.0.0.0 to reach it from the TI over the LAN)
"""
import socket, sys, time

IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240
ECHO, SGA, TTYPE, NAWS = 1, 3, 24, 31


def big_pattern():
    return bytes((i * 7) % 256 for i in range(5000))


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
        conn.sendall(chunk.replace(b'\r', b'\r\n'))  # echo (we said WILL ECHO)
        line += chunk
        while b'\r' in line:
            cmd, line = line.split(b'\r', 1)
            cmd = cmd.strip().upper()
            if cmd == b'BIG':
                conn.sendall(big_pattern().replace(bytes([IAC]), bytes([IAC, IAC])) + b'END\r\n')
            elif cmd == b'QUIT':
                conn.sendall(b'Bye\r\n')
                return


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 2323
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    addr = sys.argv[2] if len(sys.argv) > 2 else '127.0.0.1'
    s.bind((addr, port))
    s.listen(1)
    print('fake_bbs: listening on %s:%d' % (addr, port), flush=True)
    while True:
        conn, _ = s.accept()
        try:
            handle(conn)
        except OSError as e:
            print('fake_bbs:', e, flush=True)
        conn.close()


if __name__ == '__main__':
    main()
