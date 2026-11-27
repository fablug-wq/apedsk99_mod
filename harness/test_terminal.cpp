// PC harness: plays the TI side of the network terminal commands >70->73 against the real
// sketch code (setup()/loop()) and the fake BBS (fake_bbs.py on 127.0.0.1:2323).
// Every TI write to >4000->5FFF runs loop() once, as the GAL does on the real hardware.
//
// The small telnet layer below is also a prototype of what the terminal ROM has to do.
#include "Arduino.h"
#include "Ethernet.h"
#include "FTP.h"
#include <string>
#include <vector>
#include <dirent.h>
#include <unistd.h>

void setup();
void loop();
extern EthernetClient client;
extern unsigned long dsram_reads, dsram_writes;
extern int sock_maxused;

#define CALLST 0x5FC6
#define CALLBF 0x5FC8
#define ACOMND 0x5FE8

static int fails = 0, checks = 0;
#define CHECK(c, ...) do { checks++; if (c) printf("  ok   " __VA_ARGS__); \
                           else { fails++; printf("  FAIL " __VA_ARGS__); } printf("\n"); } while (0)

// ---------------------------------------------------------------- TI side
static unsigned long ti_ints;
static void ti_w(unsigned a, uint8_t v) { dsram[a - 0x4000] = v; ti_ints++; loop(); }
static uint8_t ti_r(unsigned a) { return dsram[a - 0x4000]; }
static uint8_t ti_cmd(uint8_t c) { ti_w(ACOMND, c); return ti_r(CALLST); }

static uint8_t net_connect(const char *s) {
  for (int i = 0; ; i++) { ti_w(CALLBF + i, s[i]); if (!s[i]) break; }
  return ti_cmd(0x70);
}
static bool net_send(const uint8_t *p, int n) {
  while (n > 0) {
    int k = n > 31 ? 31 : n;
    ti_w(CALLBF, k);
    for (int i = 0; i < k; i++) ti_w(CALLBF + 1 + i, p[i]);
    if (ti_cmd(0x71) != 0xFF) return false;
    p += k; n -= k;
  }
  return true;
}
static bool net_send(const char *s) { return net_send((const uint8_t *)s, strlen(s)); }
static unsigned long recv_calls;
static int net_recv(uint8_t *out) {                  // -1 = connection lost
  recv_calls++;
  ti_cmd(0x72);
  uint8_t n = ti_r(CALLBF);
  if (n == 0xFF) return -1;
  if (n > 31) return -1;                             // not a terminal firmware: never trust n blindly
  for (int i = 0; i < n; i++) out[i] = ti_r(CALLBF + 1 + i);
  return n;
}

// ---------------------------------------------------------------- telnet layer (ROM prototype)
// accept: server ECHO + SGA (character mode), our TTYPE ("ANSI") + NAWS (cols x rows); refuse the rest
enum { IAC = 255, DONT = 254, DO = 253, WONT = 252, WILL = 251, SB = 250, SE = 240 };
struct Telnet {
  int st = 0, verb = 0, cols = 40, rows = 24;
  std::vector<uint8_t> sb, out;
  std::string screen;                                // data for the screen
  void reply(std::initializer_list<int> b) { for (int c : b) out.push_back(c); }
  void feed(uint8_t c) {
    switch (st) {
      case 0: if (c == IAC) st = 1; else screen += (char)c; break;
      case 1:
        if (c == IAC) { screen += (char)0xFF; st = 0; }
        else if (c >= WILL && c <= DONT) { verb = c; st = 2; }
        else if (c == SB) { sb.clear(); st = 3; }
        else st = 0;                                 // NOP, GA, ...
        break;
      case 2:
        if (verb == DO)        { if (c == 24) reply({IAC, WILL, 24});
                                 else if (c == 31) reply({IAC, WILL, 31, IAC, SB, 31, 0, cols, 0, rows, IAC, SE});
                                 else reply({IAC, WONT, c}); }
        else if (verb == WILL) { if (c == 1 || c == 3) reply({IAC, DO, c}); else reply({IAC, DONT, c}); }
        st = 0;                                      // DONT / WONT: nothing to say
        break;
      case 3: if (c == IAC) st = 4; else sb.push_back(c); break;
      case 4:
        if (c == SE) { if (sb.size() >= 2 && sb[0] == 24 && sb[1] == 1) reply({IAC, SB, 24, 0, 'A', 'N', 'S', 'I', IAC, SE}); st = 0; }
        else { sb.push_back(c); st = 3; }
        break;
    }
  }
  bool flush() { bool ok = out.empty() || net_send(out.data(), out.size()); out.clear(); return ok; }
};

// poll RECV until `want` shows up on screen (or the connection drops / timeout)
static int pump(Telnet &t, const char *want, int ms = 3000) {
  uint8_t buf[32];
  unsigned long t0 = millis();
  while (millis() - t0 < (unsigned long)ms) {
    int n = net_recv(buf);
    if (n < 0) return -1;
    for (int i = 0; i < n; i++) t.feed(buf[i]);
    t.flush();
    if (want && t.screen.find(want) != std::string::npos) return 1;
    if (n == 0) usleep(2000);
  }
  return 0;
}

static bool ftp_has(const char *prefix) {
  DIR *d = opendir(getenv("FTPROOT")); struct dirent *e; bool found = false;
  while ((e = readdir(d))) if (!strncmp(e->d_name, prefix, strlen(prefix))) { found = true; printf("  (ftp: %s)\n", e->d_name); }
  closedir(d); return found;
}

int main() {
  setup();
  printf("setup() done, DSR %.4s loaded\n", (char *)&dsram[0x46]);

  printf("\n1. firmware detection (unknown command leaves CALLBF[0] alone)\n");
  ti_w(CALLBF, 0xFE);
  CHECK(ti_cmd(0x74) == 0xFF && ti_r(CALLBF) == 0xFE, "cmd >74: CALLST=>FF, sentinel >FE untouched");
  ti_w(CALLBF, 0xFE);
  ti_cmd(0x72);
  CHECK(ti_r(CALLBF) != 0xFE, "RECV overwrites the sentinel (=%02X: not connected)", ti_r(CALLBF));

  printf("\n2. CONNECT errors and parsing\n");
  CHECK(net_connect("127.0.0.1:1") == 2, "connection refused -> CALLST=2");
  net_connect("127.0.0.1");
  CHECK(eth_lastport == 23 && !strcmp(eth_lasthost, "127.0.0.1"), "no port -> 23 (tried %s:%u)", eth_lasthost, eth_lastport);
  net_connect("bbs.example.invalid:2323");
  CHECK(ti_r(CALLST) == 2, "unknown host -> CALLST=2");
  CHECK(!net_send("x"), "SEND without connection -> error");
  uint8_t b[32];
  CHECK(net_recv(b) == -1, "RECV without connection -> >FF");

  printf("\n3. session with the fake BBS (host name, telnet negotiation)\n");
  CHECK(net_connect("localhost:2323") == 0xFF, "CONNECT localhost:2323");
  Telnet t;
  CHECK(pump(t, "READY") == 1, "banner received");
  CHECK(t.screen.find("TTYPE ANSI") != std::string::npos, "BBS got terminal type ANSI");
  CHECK(t.screen.find("NAWS 40x24") != std::string::npos, "BBS got window size 40x24");
  CHECK(t.screen.find("NEGO DO-1 DO-3 WILL-24 WILL-31") != std::string::npos, "negotiation: DO ECHO, DO SGA, WILL TTYPE, WILL NAWS");
  CHECK(t.screen.find("\x1b[1;33mFAKE BBS") != std::string::npos, "ANSI sequences passed through untouched");
  CHECK(t.screen.find("\xC9\xCD\xCD\xBB") != std::string::npos, "CP437 bytes passed through untouched");
  CHECK(t.screen.find("IAC>\xFF<") != std::string::npos, "IAC IAC -> one >FF data byte");
  t.screen.clear();
  net_send("hello\r");
  CHECK(pump(t, "hello\r\n") == 1, "echo of typed text");

  printf("\n4. other APEDSK99 network commands during the session\n");
  ti_w(CALLBF, 0); ti_cmd(64);                       // PIO OPEN
  for (const char *p = "printed during telnet"; *p; p++) { ti_w(CALLBF, *p); ti_cmd(65); }
  ti_cmd(66);
  CHECK(ti_cmd(67) == 0xFF, "PIO CLOSE -> FTP store ok");
  CHECK(ftp_has("PRINT-"), "print file on the FTP server");
  ti_w(CALLBF, 1); ti_w(CALLBF + 1, ' '); const char *nm = "TEST";
  for (int i = 0; i < 5; i++) ti_w(CALLBF + 2 + i, nm[i]);
  CHECK(ti_cmd(33) == 0xFF, "FGET TEST -> ok");
  CHECK(access((std::string(getenv("SDROOT")) + "/DISKS/TEST.DSK").c_str(), 0) == 0, "TEST.DSK on SD");
  ti_cmd(53);
  CHECK(ti_r(CALLST) == 0xFF, "TIME() -> ok");
  sock_dump();
  t.screen.clear();
  net_send("still here?\r");
  CHECK(pump(t, "still here?") == 1, "telnet session survived print, FGET and TIME");

  printf("\n5. bulk receive (5000 bytes, IAC escaped)\n");
  t.screen.clear();
  unsigned long r0 = recv_calls, i0 = ti_ints, t0 = millis();
  net_send("BIG\r");
  CHECK(pump(t, "END\r\n", 5000) == 1, "END marker received");
  std::string exp;
  for (int i = 0; i < 5000; i++) exp += (char)((i * 7) % 256);
  size_t at = t.screen.find("BIG\r\n");
  CHECK(at != std::string::npos && t.screen.compare(at + 5, 5000, exp) == 0, "5000 bytes intact");
  printf("  RECV calls %lu, TI writes %lu, %lu ms on the PC\n", recv_calls - r0, ti_ints - i0, millis() - t0);

  printf("\n6. disconnection\n");
  t.screen.clear();
  net_send("QUIT\r");
  CHECK(pump(t, "\xFFnever", 3000) == -1 && t.screen.find("Bye") != std::string::npos, "data drained, then RECV -> >FF");
  // not checked: right after the BBS closes, the W5100 is in CLOSE_WAIT and socketSend() still
  // accepts data (as the host TCP stack here does). The ROM must detect a drop from RECV = >FF.
  printf("  info SEND right after the drop -> %s\n", net_send("x") ? "accepted (CLOSE_WAIT)" : "error");
  CHECK(ti_cmd(0x73) == 0xFF, "CLOSE");

  printf("\n7. reconnect after CLOSE\n");
  CHECK(net_connect("127.0.0.1:2323") == 0xFF, "CONNECT 127.0.0.1:2323");
  Telnet t2;
  CHECK(pump(t2, "READY") == 1, "banner again");
  CHECK(ti_cmd(0x73) == 0xFF, "CLOSE from our side");
  CHECK(net_recv(b) == -1, "RECV after CLOSE -> >FF");

  printf("\nW5100: %d socket(s) in use at most, Ethernet.begin() %d times, %d reset(s)\n",
         sock_maxused, Ethernet.begins, Ethernet.resets);
  CHECK(sock_maxused <= 4 && Ethernet.resets == 1, "never more than 4 sockets, one reset");
  printf("\n%d/%d checks passed\n", checks - fails, checks);
  return fails != 0;
}
