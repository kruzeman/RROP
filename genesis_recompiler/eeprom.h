#ifndef GENESIS_EEPROM_H
#define GENESIS_EEPROM_H
static void eeprom_init(CPU *c) {
    EEPROM *e=&c->eeprom;
    if (e->initialized) return;
    memset(e->data,0xff,sizeof e->data);
    e->initialized=1; e->sda=1; e->scl=1; e->output=1;
}
static uint8_t eeprom_read(CPU *c) {
    eeprom_init(c);
    return (uint8_t)((c->eeprom.sda && c->eeprom.output) ? 0x80:0);
}
static void eeprom_commit(EEPROM *e) {
    for (unsigned i=0;i<4;++i) if (e->dirty&(1u<<i)) e->data[e->page+i]=e->pending[i];
    e->dirty=0;
}
static void eeprom_output_bit(EEPROM *e) {
    e->output=(uint8_t)((e->data[e->address]>>(7-e->bits))&1);
}
static void eeprom_write(CPU *c, uint8_t value) {
    eeprom_init(c);
    EEPROM *e=&c->eeprom;
    uint8_t sda=!!(value&0x80), scl=!!(value&0x40);
    /* START/STOP are host transitions while the clock remains high. */
    if (e->scl && scl && sda!=e->sda) {
        if (!sda) { e->phase=EE_ADDRESS; e->bits=e->shift=0; e->output=1; ++e->starts; }
        else { eeprom_commit(e); e->phase=EE_IDLE; e->output=1; ++e->stops; }
    } else if (!e->scl && scl) {
        if (e->phase==EE_ADDRESS || e->phase==EE_WRITE) {
            e->shift=(uint8_t)((e->shift<<1)|sda);
            if (++e->bits==8) {
                if (e->phase==EE_ADDRESS) {
                    e->address=e->shift>>1; e->reading=e->shift&1;
                    e->phase=EE_ADDRESS_ACK;
                } else {
                    if (!e->dirty) e->page=e->address&0x7c;
                    e->pending[e->address&3]=e->shift; e->dirty|=1u<<(e->address&3);
                    e->address=(uint8_t)((e->address&0x7c)|((e->address+1)&3));
                    e->phase=EE_WRITE_ACK; ++e->writes;
                }
                e->ack_clock=0;
            }
        } else if (e->phase==EE_ADDRESS_ACK || e->phase==EE_WRITE_ACK) {
            e->ack_clock=1;
        } else if (e->phase==EE_READ) {
            if (++e->bits==8) {
                e->phase=EE_READ_ACK; e->ack_clock=0;
                e->address=(e->address+1)&0x7f; ++e->reads;
            }
        } else if (e->phase==EE_READ_ACK) {
            e->master_ack=!sda; e->ack_clock=1;
        }
    } else if (e->scl && !scl) {
        if (e->phase==EE_ADDRESS_ACK || e->phase==EE_WRITE_ACK) {
            if (!e->ack_clock) e->output=0;
            else {
                e->bits=e->shift=0;
                if (e->phase==EE_ADDRESS_ACK && e->reading) {
                    e->phase=EE_READ; eeprom_output_bit(e);
                } else { e->phase=EE_WRITE; e->output=1; }
            }
        } else if (e->phase==EE_READ) eeprom_output_bit(e);
        else if (e->phase==EE_READ_ACK) {
            e->output=1;
            if (e->ack_clock) {
                if (e->master_ack) { e->phase=EE_READ; e->bits=0; eeprom_output_bit(e); }
                else e->phase=EE_WAIT;
            }
        }
    }
    e->sda=sda; e->scl=scl;
}
#endif
