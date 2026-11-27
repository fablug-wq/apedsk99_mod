// PC harness: Industrial Shields FTP subset. "Server" = host folder FTPROOT (default ./ftp).
// Like the real library the control connection is never closed by the sketch, so it keeps
// its W5100 socket; each transfer opens and closes a data socket.
#pragma once
#include "Ethernet.h"
#include "SdFat.h"

extern bool ftp_up;                                 // test hook: server reachable?
class FTP {
public:
  int csock = -1;
  FTP(Client &, Client &) {}
  int connect(IPAddress, const char *, const char * = nullptr);
  size_t retrieve(const char *name, File &f);
  size_t store(const char *name, File &f);
};
