/* Host history, intentionally excluded from machine checkpoints. */
#ifndef GENESIS_RINGS_OBJECT_DIAGNOSTICS_STATE_H
#define GENESIS_RINGS_OBJECT_DIAGNOSTICS_STATE_H
enum { RINGS_OBJECT_SLOTS=56, RINGS_OBJECT_EVENTS=256 };
typedef struct {
    uint64_t step,frame;
    uint32_t pc;
    uint16_t before,after;
    uint8_t pool,slot;
} RingsObjectEvent;
typedef struct {
    uint16_t words[2][RINGS_OBJECT_SLOTS];
    uint64_t births[2][RINGS_OBJECT_SLOTS],allocations[2],releases[2],revision;
    uint32_t creators[2][RINGS_OBJECT_SLOTS];
    unsigned peak[2],next,count;
    int ready,error_latched;
    RingsObjectEvent events[RINGS_OBJECT_EVENTS];
} RingsObjectDiagnostics;
#endif
