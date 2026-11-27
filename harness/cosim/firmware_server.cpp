// APEDSK99 co-simulation, firmware side: the real sketch (with harness/mocks.cpp)
// as a process that the emulated TI talks to through two FIFOs.
//
//   firmware_server <cmd_fifo> <reply_fifo>
//
// At start (and after a reset, ADSR/ARST): setup(), then the whole DSR RAM is sent.
// Then, for every word the TI writes into >4000->5FFF (the GAL's TI_INT: it decodes
// A15 = 0, so a word write, two byte cycles on the 8-bit bus, signals once):
//   cmd   'W' addr_hi addr_lo even_byte odd_byte     (addr = even offset from >4000)
//   reply n_hi n_lo, then n x (addr_hi addr_lo value): the bytes the firmware wrote
// The TI is halted while the firmware runs, as on the hardware.
// SDROOT, FTPROOT: the SD card and FTP server folders; EEPROM_FILE: the EEPROM.
#include "Arduino.h"
#include <fcntl.h>
#include <unistd.h>
#include <vector>

void setup();
void loop();
extern void (*dsram_hook)(unsigned);
extern void (*reset_hook)();

static int fin, fout;
static char **gargv;
static bool dirty[0x2000];
static std::vector<uint16_t> changed;

static void mark(unsigned a) { if (!dirty[a]) { dirty[a] = true; changed.push_back(a); } }

static void readn(uint8_t *b, size_t n) {
  while (n) { ssize_t r = read(fin, b, n); if (r <= 0) exit(0); b += r; n -= r; }
}
static void reply(const std::vector<uint16_t> &list) {
  std::vector<uint8_t> out = { uint8_t(list.size() >> 8), uint8_t(list.size()) };
  for (uint16_t a : list) { out.push_back(a >> 8); out.push_back(a & 0xFF); out.push_back(dsram[a]); }
  size_t done = 0;
  while (done < out.size()) { ssize_t r = write(fout, out.data() + done, out.size() - done); if (r <= 0) exit(0); done += r; }
}

static void do_reset() {                             // like the watchdog: start again, keep the DSR choice
  setenv("APEDSK_RESET", "1", 1);
  close(fin); close(fout);
  execv("/proc/self/exe", gargv);
  _exit(4);
}

int main(int argc, char **argv) {
  if (argc < 3) { fprintf(stderr, "usage: firmware_server <cmd_fifo> <reply_fifo>\n"); return 1; }
  gargv = argv;
  setvbuf(stdout, nullptr, _IONBF, 0);
  fin = open(argv[1], O_RDONLY);
  fout = open(argv[2], O_WRONLY);
  if (getenv("APEDSK_RESET")) DSRreset = DSRRESETMAGIC;
  reset_hook = do_reset;
  setup();
  std::vector<uint16_t> all(0x2000);
  for (int i = 0; i < 0x2000; i++) all[i] = i;
  reply(all);
  dsram_hook = mark;
  for (;;) {
    uint8_t c[5];
    readn(c, 1);
    if (c[0] != 'W') { fprintf(stderr, "firmware_server: bad command %d\n", c[0]); return 1; }
    readn(c + 1, 4);
    unsigned a = ((c[1] << 8) | c[2]) & 0x1FFE;
    dsram[a] = c[3];
    dsram[a + 1] = c[4];
    loop();
    reply(changed);
    for (uint16_t x : changed) dirty[x] = false;
    changed.clear();
  }
}
