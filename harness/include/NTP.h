// PC harness: NTP stub (fixed time). Like the real sketch, the UDP socket stays allocated.
#pragma once
#include "Ethernet.h"
extern bool ntp_up;
class NTP {
public:
  EthernetUDP &udp;
  NTP(EthernetUDP &u) : udp(u) {}
  bool begin() { return udp.begin(123); }
  void stop() { udp.stop(); }
  bool request(const char *) { return ntp_up && udp.sock >= 0; }
  int available() { return 1; }
  uint32_t read() const { return 1795000000UL; }  // 2026-11-17
};
