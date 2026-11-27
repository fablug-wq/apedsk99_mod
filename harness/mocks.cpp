// PC harness: implementation of the mocks (HAL, SD, EEPROM, Ethernet, FTP)
#include "Arduino.h"
#include "SdFat.h"
#include "EEPROM.h"
#include "Ethernet.h"
#include "FTP.h"
#include <time.h>
#include <unistd.h>
#include <fcntl.h>
#include <poll.h>
#include <errno.h>
#include <netdb.h>
#include <arpa/inet.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <netinet/tcp.h>

// ---------------------------------------------------------------- time
unsigned long millis() {
  struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
  return ts.tv_sec * 1000UL + ts.tv_nsec / 1000000UL;
}
void delay(unsigned long ms) { usleep(ms * 1000); }
void delayMicroseconds(unsigned int) {}
char *ltoa(long v, char *buf, int) { sprintf(buf, "%ld", v); return buf; }

// ---------------------------------------------------------------- HAL
uint8_t PORTB, PORTC, PORTD, DDRB, DDRC, DDRD, PINB, PINC, PIND;   // PIND bit 2 = 0: TI_INT active
unsigned int DSRreset;
uint8_t dsram[0x2000];
unsigned long dsram_reads, dsram_writes;
byte read_DSRAM(unsigned int a) { dsram_reads++; return dsram[(a - 0x4000) & 0x1FFF]; }
void write_DSRAM(unsigned int a, byte d) { dsram_writes++; dsram[(a - 0x4000) & 0x1FFF] = d; }
void TIstop() {}
void TIgo() {}
void NOP() {}
void IAQ() {}
void APEDSK99reset() { printf("APEDSK99reset()\n"); exit(2); }
void Flasher(byte e) { printf("Flasher(%d)\n", e); exit(3); }

EEPROMClass EEPROM;

// ---------------------------------------------------------------- SD
std::string sdpath(const char *p) {
  const char *root = getenv("SDROOT") ? getenv("SDROOT") : "sd";
  while (*p == '/') p++;
  std::string s = std::string(root) + "/" + p;
  if (s.size() > 1 && s.back() == '/') s.pop_back();
  return s;
}
bool SdFat::exists(const char *p) { struct stat st; return stat(sdpath(p).c_str(), &st) == 0; }
File SdFat::open(const char *p, uint8_t mode) {
  File f; f.path = sdpath(p);
  struct stat st;
  if (stat(f.path.c_str(), &st) == 0 && S_ISDIR(st.st_mode)) { f.dp = opendir(f.path.c_str()); f.dir = true; return f; }
  if (mode & O_TRUNC)            f.fp = fopen(f.path.c_str(), "w+b");
  else if (mode & O_WRITE) {     f.fp = fopen(f.path.c_str(), "r+b");
                                 if (!f.fp && (mode & O_CREAT)) f.fp = fopen(f.path.c_str(), "w+b");
                                 if (f.fp && (mode & O_AT_END)) fseek(f.fp, 0, SEEK_END); }
  else                           f.fp = fopen(f.path.c_str(), "rb");
  return f;
}
File File::openNextFile() {
  File f;
  if (!dp) return f;
  struct dirent *e;
  while ((e = readdir(dp)) && e->d_name[0] == '.') {}
  if (!e) return f;
  f.path = path + "/" + e->d_name;
  struct stat st; stat(f.path.c_str(), &st);
  if (S_ISDIR(st.st_mode)) { f.dp = opendir(f.path.c_str()); f.dir = true; }
  else f.fp = fopen(f.path.c_str(), "rb");
  return f;
}

// ---------------------------------------------------------------- W5100 sockets
static const char *sockowner[MAX_SOCK_NUM];
int sock_maxused = 0;
int sock_inuse() { int n = 0; for (auto o : sockowner) n += o != nullptr; return n; }
int sock_alloc(const char *owner) {
  for (int i = 0; i < MAX_SOCK_NUM; i++) if (!sockowner[i]) {
    sockowner[i] = owner;
    if (sock_inuse() > sock_maxused) sock_maxused = sock_inuse();
    return i;
  }
  printf("  [W5100] no free socket for %s\n", owner); sock_dump();
  return -1;
}
void sock_free(int s) { if (s >= 0) sockowner[s] = nullptr; }
void sock_dump() {
  printf("  [W5100] sockets:");
  for (auto o : sockowner) printf(" %s", o ? o : "-");
  printf("\n");
}

EthernetClass Ethernet;
void EthernetClass::begin(uint8_t *, uint8_t *) {
  begins++;
  if (resets == 0) {                                 // W5100.init(): soft reset only the first time
    resets++;
    for (auto &o : sockowner) o = nullptr;
  }
}

char eth_lasthost[64];
uint16_t eth_lastport;

int EthernetClient::connect(const char *host, uint16_t port) {
  strncpy(eth_lasthost, host, 63); eth_lastport = port;
  if (sock >= 0) stop();                             // library: disconnect the previous socket
  struct in_addr ia;
  if (!inet_aton(host, &ia)) {                       // DNS query needs a UDP socket for a moment
    int d = sock_alloc("dns"); if (d < 0) return 0; sock_free(d);
  }
  struct addrinfo hints = {}, *res;
  hints.ai_family = AF_INET; hints.ai_socktype = SOCK_STREAM;
  char ps[8]; sprintf(ps, "%u", port);
  if (getaddrinfo(host, ps, &hints, &res) != 0) return 0;
  sock = sock_alloc(owner);
  if (sock < 0) { freeaddrinfo(res); return 0; }
  fd = socket(AF_INET, SOCK_STREAM, 0);
  fcntl(fd, F_SETFL, O_NONBLOCK);
  int r = ::connect(fd, res->ai_addr, res->ai_addrlen);
  freeaddrinfo(res);
  if (r < 0 && errno == EINPROGRESS) {
    struct pollfd p = { fd, POLLOUT, 0 };
    if (poll(&p, 1, timeout) == 1) { int err; socklen_t l = sizeof err; getsockopt(fd, SOL_SOCKET, SO_ERROR, &err, &l); r = err ? -1 : 0; }
  }
  if (r < 0) { stop(); return 0; }
  return 1;
}
size_t EthernetClient::write(const uint8_t *buf, size_t n) {
  if (fd < 0) return 0;
  size_t done = 0;
  while (done < n) {
    ssize_t r = send(fd, buf + done, n - done, MSG_NOSIGNAL);
    if (r < 0 && errno == EAGAIN) { struct pollfd p = { fd, POLLOUT, 0 }; poll(&p, 1, 100); continue; }
    if (r <= 0) return 0;
    done += r;
  }
  return n;
}
int EthernetClient::available() {
  if (fd < 0) return 0;
  int n = 0; ioctl(fd, FIONREAD, &n);
  if (n > 2048) n = 2048;                            // W5100 RX buffer with 4 sockets
  return n;
}
int EthernetClient::read(uint8_t *buf, size_t n) { return fd < 0 ? -1 : recv(fd, buf, n, 0); }
uint8_t EthernetClient::connected() {
  if (fd < 0) return 0;
  uint8_t c; ssize_t r = recv(fd, &c, 1, MSG_PEEK | MSG_DONTWAIT);
  if (r > 0) return 1;                               // data left: still "connected" (CLOSE_WAIT && available)
  if (r == 0) return 0;                              // closed by the other side, nothing left
  return errno == EAGAIN || errno == EWOULDBLOCK;
}
void EthernetClient::stop() { if (fd >= 0) close(fd); fd = -1; sock_free(sock); sock = -1; }

// ---------------------------------------------------------------- FTP
bool ftp_up = true, ntp_up = true;
static std::string ftppath(const char *n) { return std::string(getenv("FTPROOT") ? getenv("FTPROOT") : "ftp") + "/" + n; }
int FTP::connect(IPAddress, const char *, const char *) {
  if (!ftp_up) return 0;
  if (csock < 0) csock = sock_alloc("ftpControl");  // stays open, as with the real sketch
  return csock >= 0;
}
size_t FTP::retrieve(const char *name, File &f) {
  int d = sock_alloc("ftpData"); if (d < 0) return 0;
  FILE *src = fopen(ftppath(name).c_str(), "rb"); size_t n = 0; int c;
  if (src) { while ((c = fgetc(src)) != EOF) { f.write(c); n++; } fclose(src); }
  sock_free(d); return n;
}
size_t FTP::store(const char *name, File &f) {
  int d = sock_alloc("ftpData"); if (d < 0) return 0;
  FILE *dst = fopen(ftppath(name).c_str(), "wb"); size_t n = 0; int c;
  while ((c = f.read()) != -1) { fputc(c, dst); n++; }
  fclose(dst); sock_free(d); return n;
}
