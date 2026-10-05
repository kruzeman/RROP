# Gamepads

[Русская версия](gamepads-ru.md) · [Manual](usage.md)

The SDL2 window build supports one controller recognized by SDL's GameController
API. No additional build flag or library is required. Input is enabled by default
in Classic and Enhanced. Headless builds do not accept physical controllers.

Connect before or during play. RROP opens the first recognized controller; if it
is unplugged, RROP releases its input and looks for another connected controller.
Keyboard controls remain available alongside it. System → Help controls only
the original on-screen controller drawing.

## Default layout

Names below use SDL's standard Xbox-style button positions. On PlayStation
controllers, X/A/B correspond to Square/Cross/Circle respectively.

| Controller input | Action |
| --- | --- |
| D-pad or left stick | Genesis directions |
| X / A / B | Genesis A / B / C |
| Start | Genesis Start |
| Back / Select | Open Settings |
| LB / RB | Open manual save / load chooser |

These shortcuts target the added host menus. Original game menus continue to
receive Genesis buttons. In Settings and save/load menus, D-pad or left stick
selects items, A/X/Start confirms and B/Back returns. Move the stick back to its
center between menu steps; holding it does not repeat navigation.

## Control settings

Open Settings → Control settings to enable/disable controller input, see the
connected device's name, or select the alternate mapping: controller A/B/X →
Genesis A/B/C. **Assign buttons: A / B / C / START** opens a four-step wizard:
press the controller button you want for each Genesis action, releasing it
between steps. The current action is highlighted on the parchment. All four
bindings are applied and saved together when START is assigned.

Escape on the keyboard or Back/Select on the controller cancels the wizard
without changing the current layout. Disconnecting the controller or losing
window focus also cancels. Duplicate bindings are rejected. D-pad, Back,
Guide/Home and LB/RB remain reserved for movement and host-menu shortcuts;
analog axes/triggers cannot be assigned as buttons. Host-menu navigation keeps
its fixed A/X/Start confirm and B/Back cancel controls, independently of the
chosen Genesis layout. Keyboard Z/X/C/Enter is unchanged.

**Reset buttons** restores X/A/B plus Start. Choosing a preset also replaces a
custom layout. Preferences persist in `settings.cfg` as `gamepad`, `pad_layout`,
`pad_custom`, `pad_a`, `pad_b`, `pad_c` and `pad_start`, independently of saved game
slots. Old files remain compatible. Invalid or incomplete custom bindings fall
back to the selected preset. SDL button names describe logical positions;
these settings apply to the active controller and remain available after
reconnecting or restarting RROP.

Disabling the controller also disables its menu shortcuts. Use the keyboard to
enable it again. Keyboard input remains active when the controller is disabled.

The left stick has a dead zone (about 30% to engage, 24% to release) to limit
drift. Opposite directions cancel. Opening/closing host menus, pausing, loading a
save or losing window focus clears gameplay input: release held controller buttons
before pressing them again. This prevents a menu confirmation from becoming an
unintended action after returning to the game.

## Troubleshooting

If the device is absent from Control settings, check that the OS can see it and
that SDL2 recognizes its mapping. Unknown devices can use a mapping supplied
through SDL's `SDL_GAMECONTROLLERCONFIG` environment variable. RROP does not
download a mapping database and does not fall back to raw joystick input.
Button labels on Nintendo controllers can differ from SDL's logical positions.

Physical controller behavior still needs hardware verification on each platform.
