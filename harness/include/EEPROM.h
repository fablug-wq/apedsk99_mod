// PC harness: EEPROM as a RAM array
#pragma once
#include "Arduino.h"
struct EEPROMClass {
  uint8_t mem[1024];
  EEPROMClass();
  void save();
  uint8_t read(int a) { return mem[a]; }
  void write(int a, uint8_t v) { mem[a] = v; save(); }
  template <class T> void put(int a, const T &t) { memcpy(mem + a, &t, sizeof t); save(); }
  template <class T> void get(int a, T &t) { memcpy(&t, mem + a, sizeof t); }
};
extern EEPROMClass EEPROM;
