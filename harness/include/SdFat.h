// PC harness: SdFat 1.x subset on top of a host folder (SDROOT, default ./sd)
#pragma once
#include "Arduino.h"
#include <dirent.h>
#include <string>

#define O_READ   0x01
#define O_WRITE  0x02
#define O_RDWR   (O_READ | O_WRITE)
#define O_CREAT  0x10
#define O_TRUNC  0x20
#define O_AT_END 0x40
#define FILE_READ  O_READ
#define FILE_WRITE (O_RDWR | O_CREAT | O_AT_END)
#define T_WRITE 2

struct dir_t { uint16_t lastWriteDate, lastWriteTime; };
#define FAT_YEAR(d)   (1980 + ((d) >> 9))
#define FAT_MONTH(d)  (((d) >> 5) & 0xF)
#define FAT_DAY(d)    ((d) & 0x1F)
#define FAT_HOUR(t)   ((t) >> 11)
#define FAT_MINUTE(t) (((t) >> 5) & 0x3F)

std::string sdpath(const char *p);

class File {
public:
  FILE *fp = nullptr;
  DIR *dp = nullptr;
  std::string path;
  bool dir = false;
  File() {}
  operator bool() const { return fp || dp; }
  int read() { return fp ? fgetc(fp) : -1; }
  size_t write(uint8_t c) { return fp ? fputc(c, fp) != EOF : 0; }
  int available() { if (!fp) return 0; long p = ftell(fp); fseek(fp, 0, SEEK_END); long e = ftell(fp); fseek(fp, p, SEEK_SET); return e - p; }
  bool seek(unsigned long pos) { return fp && fseek(fp, pos, SEEK_SET) == 0; }
  unsigned long position() { return fp ? ftell(fp) : 0; }
  unsigned long size() { if (!fp) return 0; long p = ftell(fp); fseek(fp, 0, SEEK_END); long e = ftell(fp); fseek(fp, p, SEEK_SET); return e; }
  void flush() { if (fp) fflush(fp); }
  void close() { if (fp) fclose(fp); if (dp) closedir(dp); fp = nullptr; dp = nullptr; }
  bool rename(const char *np) { flush(); return ::rename(path.c_str(), sdpath(np).c_str()) == 0 && ((path = sdpath(np)), true); }
  bool isDirectory() { return dir; }
  bool getName(char *buf, size_t n) { std::string b = path.substr(path.rfind('/') + 1); strncpy(buf, b.c_str(), n - 1); buf[n-1] = 0; return true; }
  bool dirEntry(dir_t *) { return false; }
  bool timestamp(uint8_t, uint16_t, uint8_t, uint8_t, uint8_t, uint8_t, uint8_t) { return true; }
  File openNextFile();
};
typedef File SdFile;

class SdFat {
public:
  bool begin(uint8_t) { return true; }
  bool exists(const char *p);
  File open(const char *p, uint8_t mode = O_READ);
  bool remove(const char *p) { return ::remove(sdpath(p).c_str()) == 0; }
};
