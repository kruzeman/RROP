# Movement response

Enhanced reduces outdoor response latency without changing CPU, VDP or audio
clock rates, skipping native instructions, or increasing world update frequency.
Classic keeps the original controller and presentation behavior.

## Where the delay occurs

On the verified ROM, the VBlank handler at `$001272` waits for three stable
samples and queues controller snapshots. The main-game decoder at `$012FF8`
reads them only after the native drawing pass. A press less than about 50 ms
before a read can miss that read and wait another complete turn.

On a copy of Manual Save 3, the command was enqueued at `$01E3B0` and resolved
by the native actor update in the same turn. Reading the command to changing
camera coordinates took approximately 18 ms; the movement queue did not impose
another full turn in this scenario.

The host renderer already prepares a completed scene on a disposable CPU copy
at `$01B950`. Previously it held that result until the native bitmap upload
returned at `$01B9EE`, about 350–400 ms later. This was avoidable display latency,
not required simulation work.

## Changes

- At the existing decoder boundary, Enhanced uses the currently held keyboard
  or gamepad direction. A short press survives until one decision, even when
  press/release events arrive in one SDL poll. A consumed press cannot be
  repeated by an older native FIFO snapshot. Action buttons, native menus,
  dialogues and auto-walk retain the native path. Pause, lost focus, settings
  and loading clear pending host intent.
- A complete replay of a stable outdoor scene is published at the drawing
  boundary for the next video frame. Initial scenes, changed map identity or
  tile bank, dialogues, fixed rooms and incomplete replays retain the original
  upload boundary. The live game still executes every original instruction.
- Enhanced retains its scene layer at 100% with wide view and smoothing disabled,
  so the response improvement does not require zooming out. Classic does not
  activate that layer.

## Measurement

The local test used a copy of Manual Save 3 and the verified ROM SHA-256
`36303fc447c433ebc69c3d4df86c783c86b383e0acead1c19595f13269e248f5`.
After two seconds of settling, it held Right for two seconds, then released.
Nine starting phases were sampled at offsets 0, 3, 6, 9, 12, 15, 17, 18 and 21
video frames. Results are modeled console time to the first video snapshot
with resolved new coordinates, not physical keyboard-to-monitor latency.

| Response | Original | Enhanced |
| --- | ---: | ---: |
| Minimum | 482 ms | 48 ms |
| Mean | 667 ms | 202 ms |
| Maximum | 815 ms | 365 ms |
| Successive movement intervals | 367–417 ms | 367–417 ms |

For each phase, the presentation change alone produced identical native
movement times, RAM, elapsed console time, game-clock increments and actor-update
counts. Full Enhanced can accept a direction one turn earlier; that changes the
initial phase and sometimes the terrain drawn during the measurement, rather
than increasing the movement cadence. No execution or replay failures occurred.

In the default Enhanced path, the remaining latency is the wait for the native command-reading boundary.
Consistently sub-100-ms response would require separating player input/movement
from the native turn loop. These changes do not claim to complete that larger
rewrite. SDL polling, host replay cost, display synchronization and camera
smoothing can also affect physical visible response.

## Withdrawn experiment

The earlier drawing-clock acceleration was withdrawn: it shortened the native
turn loop and accelerated game time, actors and animations. Lower response
measurements alone were insufficient validation. That acceleration is absent
from this change; existing checkpoints remain compatible.

## Validation

All six new response regressions pass, including an actual SDL pixel read at
100% with wide view and smoothing disabled. The complete suite runs 377 tests:
358 pass, 13 skip, and the same six pre-existing failures remain (one SDL audio
event test, four gamepad remapping tests and one GCC format-truncation test in
the save hook). There are no additional failures.

The rebuilt SDL/audio executable loads the copied Manual Save 3 and runs its
instruction budget with zero wide replay failures and a visible outdoor scene.
The embedded ROM and all translated M68K/Z80 instruction code are byte-for-byte
identical to the original translation. The original user save is unchanged.

An opt-in implementation of separate player/world scheduling is documented in
[responsive-movement.md](responsive-movement.md).
