// PC harness: minimal Arduino environment for the APEDSK99 sketch.
// The sketch tabs are compiled unchanged, except the -B-HAL.ino tab which is replaced
// by the functions below (DSR RAM is a plain array, TI_INT is a bit in a fake PIND).
#pragma once
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "binary.h"

typedef uint8_t byte;
typedef bool boolean;
typedef uint16_t word_t;
inline uint16_t word(uint8_t h, uint8_t l) { return (h << 8) | l; }

#define PROGMEM
#define PSTR(s) (s)
#define F(s) ((const __FlashStringHelper *)(s))
class __FlashStringHelper;
#define strcpy_P strcpy
#define strchr_P strchr
#define pgm_read_byte(p) (*(const uint8_t *)(p))

unsigned long millis();
void delay(unsigned long ms);
void delayMicroseconds(unsigned int us);
inline void noInterrupts() {}
inline void interrupts() {}
char *ltoa(long v, char *buf, int base);

// fake AVR ports (only TI_INT = PD2 matters)
extern uint8_t PORTB, PORTC, PORTD, DDRB, DDRC, DDRD, PINB, PINC, PIND;

// ---- replacement for the -B-HAL.ino tab
#define CLOCK     17
#define LATCH     18
#define DS        19
#define CE        14
#define WE        16
#define TI_READY   3
#define TI_INT     2
#define TI_BUFFERS 15
#define DSRRESETMAGIC 0xA599
extern unsigned int DSRreset;
extern uint8_t dsram[0x2000];                       // >4000->5FFF
byte read_DSRAM(unsigned int address);
void write_DSRAM(unsigned int address, byte data);
void TIstop();
void TIgo();
void NOP();
void IAQ();
void APEDSK99reset();
void Flasher(byte errorcode);

// minimal IPAddress
class IPAddress {
public:
  uint8_t a[4];
  IPAddress() { memset(a, 0, 4); }
  IPAddress(uint8_t x, uint8_t y, uint8_t z, uint8_t w) { a[0]=x; a[1]=y; a[2]=z; a[3]=w; }
  IPAddress(const uint8_t *p) { memcpy(a, p, 4); }
};
