# Experimental independent player scheduling

Enable with `./run-rings-of-power.sh --responsive-movement` and select Enhanced
in Settings. Without this launch flag, the accepted scene/input improvements
in [responsiveness.md](responsiveness.md) remain the default. Classic does not
activate the new scheduler. Build with the normal verified-ROM build command.

## Scheduling

The native world loop is suspended at `$00D2BE` until its next turn deadline.
Ordinary cardinal keyboard/gamepad movement can resolve there immediately via
the translated original `$024984` procedure, including its collision checks.
The same held direction is rate-limited; a short press is consumed once.
The native main-game decoder suppresses duplicate keyboard directions while
this path is active. Mouse injection and combined directions keep their native
path; queued action buttons retain their original edges.

Bitmap instructions execute with available host CPU capacity instead of
consuming real device time. An isolated reference traversal measures their
original elapsed console clocks, including native interrupts and VBlank waits.
Those clocks, the normal world-loop work, and the separate player's native
work are included in the next world deadline. This preserves the terrain-
dependent original turn cadence. Live VDP, Z80 and audio clocks continue to
advance normally during the suspended loop. World clock and NPC updates still
run only through their original turn procedures.

Player resolution uses a disposable CPU copy. A completed ordinary step applies
its RAM changes, preserving the suspended CPU registers and stack. Effects on
other actors, hardware, game time, map identity or native menu/event modes reject
the early transaction and retain its direction for the original command path.
Vehicles, scripted movement and nonempty actor queues also use that fallback.
The six entry boundaries have ROM opcode guards, in addition to the build's
full-ROM SHA-256 verification. A failed reference traversal keeps stock timing.

Loading reattaches the session's opt-in and input intent, with cleared deadlines.
Lost focus, pause, settings and actions cancel stale direction fallback. No
scheduler fields or host intent are added to the cartridge save format.

## Evidence and limits

On a copy of Manual Save 3, nine starting phases of a two-second Right hold
showed the first changed scene about 14 ms after the press in modeled console
time. Subsequent steps were about 367–417 ms apart. The first step happens earlier,
so a fixed two-second hold can naturally contain one additional step.
A six-second idle comparison produced 15 world-clock updates and 16 actor passes
in both versions. A longer comparison measured 100 native world turns (one
game hour): 38.232567 seconds with stock scheduling and 38.232568 seconds with
independent scheduling on this save. Both runs ended with 102 world-clock
updates and 103 actor passes over 39.3676 seconds. Up moves and Down/Left collisions were checked separately;
no replay or execution faults occurred.

These are console-time measurements, not physical keyboard-to-monitor latency.
Rendering still occupies host CPU time, and display/camera smoothing adds latency.
The mode is opt-in because only this outdoor save and synthetic regressions have
been checked; encounters, vehicles, long sessions and map transitions need wider
playtesting before changing the default.

## Validation

The rebuilt executable was smoke-tested with the SDL dummy video/audio drivers
on a copied Manual Save 3 in both Enhanced and Classic. An actual-ROM harness
using SDL key events also checked a 33 ms tap at two starting phases, a held
Right direction, changing Right to Left, focus loss, an action alongside movement,
switching to Classic, and reloading the save while moving. Taps resolved once;
release/focus loss produced no further steps, the reversed direction respected
its blocked tile, and reload restored the saved coordinates with no stale intent.
No execution, scene replay or reference timing failures were reported.

All 12 responsiveness/scheduler regression tests pass. The complete suite ran
383 tests: 364 passed, 13 skipped, and six previously observed failures remain
(one synthetic SDL audio event test, four gamepad remapping event tests, and a
save-test compile warning promoted to an error by GCC 16). The ROM bytes and
translated instruction bodies remain unchanged; only runtime/adapters were edited.
