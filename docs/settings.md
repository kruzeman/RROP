# Settings

[Русская версия](settings-ru.md) · [Manual](usage.md)

Open Settings from the sixth main-menu item, **System → Settings**, **F10**,
or **Esc** during gameplay. The host menu uses the game's parchment styling.
The original game menus and the added host menus remain separate.

**Mode: Classic** selects the original viewport, pixel font.
Keyboard and gamepad input, and Control settings, are available in both modes.
Saves remain available. **Mode: Enhanced** exposes these options:

| Option | Behavior |
| --- | --- |
| Widescreen | Expanded outdoor world; HUD displayed over it |
| Fullscreen | Desktop fullscreen |
| Smooth map | Interpolated outdoor camera scrolling |
| Zoom | Mouse-wheel zoom between 50% and 100% |
| Mouse controls | Left-button movement; right-button native automatic walking |
| Control settings | Gamepad toggle and Genesis A/B/C layout; available in both modes |

[Gamepad controls](gamepads.md) lists mappings and supported controllers.

Back and Exit are available in both modes. Up/Down selects a row; Enter, X,
Z or Left/Right changes it. Esc returns; F10 closes Settings. The game and
autosave timer pause while the host menu is open.

Interiors and battles retain the original viewport and 100% zoom, even in
Enhanced mode. The selected outdoor zoom returns on leaving those scenes.
Zoom does not change the game's simulation speed. Smooth scrolling is a
presentation feature; the native game still updates its decisions at its own rate.

Preferences are saved immediately in `settings.cfg` beside the slots.
They take precedence over launch defaults and are not replaced when a save
is loaded. Delete only `settings.cfg`, with the game closed, to reset defaults.

**System → Help** toggles the original controller hint. It defaults to off;
the choice persists in `settings.cfg` as `help=0` or `help=1`. This controls
an on-screen graphic, not physical gamepad input.

External fonts require building with `--text-renderer rings-text` and launching
with `--font /path/to/font.ttf`. Other window features are compiled by default.
See [the manual](usage.md) for build and launch examples.
