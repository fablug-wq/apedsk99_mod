// PC harness: Ethernet 2.0.x subset. EthernetClient uses real host TCP sockets.
// Models the behaviour checked in the real library:
//  - Ethernet.begin() resets the W5100 (closing every socket) only the first time,
//  - the W5100 has 4 sockets: running out makes connect() / begin() fail.
#pragma once
#include "Arduino.h"

#define MAX_SOCK_NUM 4
int  sock_alloc(const char *owner);                 // -1 if none free
void sock_free(int s);
int  sock_inuse();
void sock_dump();

class Client {};

class EthernetClient : public Client {
public:
  int fd = -1, sock = -1;
  uint16_t timeout = 1000;
  const char *owner;
  EthernetClient(const char *o = "client") : owner(o) {}
  void setConnectionTimeout(uint16_t t) { timeout = t; }
  int connect(const char *host, uint16_t port);
  size_t write(const uint8_t *buf, size_t n);
  int available();
  int read(uint8_t *buf, size_t n);
  uint8_t connected();
  void stop();
};

class EthernetUDP {
public:
  int sock = -1;
  uint8_t begin(uint16_t) { if (sock < 0) sock = sock_alloc("udp"); return sock >= 0; }
  void stop() { if (sock >= 0) sock_free(sock); sock = -1; }
};

class EthernetClass {
public:
  int begins = 0, resets = 0;
  void init(uint8_t) {}
  void begin(uint8_t *mac, uint8_t *ip);
};
extern EthernetClass Ethernet;

// test hooks: last port a CONNECT tried, and the host
extern char     eth_lasthost[64];
extern uint16_t eth_lastport;
