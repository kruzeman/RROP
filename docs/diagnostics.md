# Native Void-error diagnostics

[Русская версия](diagnostics-ru.md)

The original message “Void has found your party…” is a generic internal-error
screen. The number inserted before `seconds` is an error code, not elapsed
time. Multiple conditions reach the same handler.

Confirmed calls include:

| Code | Condition |
| --- | --- |
| 22 / `0x16` | No free entry in the 56-slot placement table |
| 26 / `0x1a` | No free entry in the 56-slot actor table |
| 24 / `0x18` | Object absent from the placement cache |

This identifies possible failure mechanisms. It does not yet prove which one
causes the reported failure after extended gameplay.

## Capture

Normal Rings builds enable diagnostics with save support. Rebuild after
updating source; existing binaries do not gain the feature automatically.
No extra launch option is needed.

The host records the last 256 slot-header changes across both tables, with
the writing instruction's PC, frame and execution step. It also counts
free-to-occupied and occupied-to-free transitions and peak occupancy.
Actor entries are occupied when the header's low nibble is nonzero;
placement entries are occupied when their first word is not 9999.

History starts at gameplay entry and resets when a checkpoint is loaded.
Existing objects' creation locations are unknown (`created_pc=000000`).
Counts describe observed slot-state transitions, not every high-level object
creation or update.

Before entry into the original error handler at `$012FA0`, the host writes:

- `diagnostics/void-error.txt`: native error code, return PC, CPU registers,
  both raw object tables and recent history;
- `diagnostics/void-error.grs`: machine checkpoint before drawing the fatal screen,
  when the state can be serialized successfully.

The `diagnostics` directory is inside the save directory; the terminal prints
the report's exact location. Each later error replaces this diagnostic pair.
Manual slots and autosaves are not overwritten. The report records
`snapshot=FAILED` if capture fails.

The text report is intended for investigation. A full `.grs` file contains
game memory and extracted presentation data; keep it out of public issues
and the source repository.

## What this does not fix

The monitor neither clears tables nor suppresses the original failure.
An emergency checkpoint reproduces the impending error; it is not a repaired save.

Our normal saves also restore RAM exactly. The original EEPROM load calls
`$020CF6` and `$023A9E` to reset temporary tables before rebuilding game state.
Our checkpoint loader does not repeat that cleanup.

The next step is to identify occupied records that should have been released,
trace their creation/release routines, and fix a confirmed lifetime error.
Blindly clearing records risks losing a character, item or quest state.

This initial diagnostic implementation has undergone static review only;
build and gameplay checks have not yet been run.
