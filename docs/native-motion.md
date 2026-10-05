# Camera and hero motion

[Русская версия](native-motion-ru.md) · [Settings](settings.md)

Enable **Enhanced → Smooth map** or launch with `--smooth-camera`. In this
branch, camera smoothing also works in native indoor scenes. The original
viewport, clipping and 100% zoom remain in use; the outdoor zoom returns on exit.
A room with a fixed camera does not pan just because the hero moves.

The actor implementation smooths the primary exploration hero outdoors and
inside native scenes, including the shadow when the game draws one. A completed movement gets a finite visual transition
(200 ms by default); it does not predict movement or change input, coordinates,
collisions, interactions or CPU timing. Releasing input can still leave the
current visual transition to finish. It does not request additional steps.

Use `--smooth-camera --camera-smooth-ms 120` for a shorter transition, or turn
Smooth map off for the original presentation. Pause and host menus freeze the
transition. Loading a slot, changing scenes, disabling smoothing and large
coordinate jumps reset interpolation. Existing save files remain readable;
motion caches are reconstructed at the next completed redraw.

The renderer captures only the original 10×10 traversal for indoor exploration.
Combat uses the original frame, including every party member and enemy,
regardless of the Smooth map setting.
It redraws resources rather than copying a rectangle containing the hero and
floor. Draw order comes from the latest submitted frame: wall occlusion while
crossing a tile boundary needs visual verification. NPCs and the rest of the
party do not yet have independent interpolation. Outdoor
hero motion uses a bounded draw-command patch with matching ground ownership,
so zoom clipping follows the interpolated hero and its shadow. Mouse directions
use the displayed hero position. Widescreen and outdoor zoom from 50% to 100%
are supported. Overflowing command capture falls back to the original bitmap.
The original animation poses
are retained; this does not generate additional walk animation frames.

Regression tests cover indoor camera coordinates, indoor party poses without an
outdoor shadow, elevated object ownership, SDL presentation and combat parity
with smoothing disabled. A local verified-ROM probe also checks indoor hero
transitions and the original bitmap; these checks do not replace full playtesting.
