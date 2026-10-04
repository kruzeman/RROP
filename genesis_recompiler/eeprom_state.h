#ifndef GENESIS_EEPROM_STATE_H
#define GENESIS_EEPROM_STATE_H
/* EA X24C01: 128 bytes, direct 7-bit address + R/W, four-byte write page. */
enum { EE_IDLE, EE_ADDRESS, EE_ADDRESS_ACK, EE_WRITE, EE_WRITE_ACK, EE_READ, EE_READ_ACK, EE_WAIT };
typedef struct {
    uint8_t data[128], pending[4], dirty, page;
    uint8_t enabled, initialized, sda, scl, output, phase, bits, shift, address, reading, ack_clock, master_ack;
    uint64_t starts, stops, reads, writes;
} EEPROM;
#endif
