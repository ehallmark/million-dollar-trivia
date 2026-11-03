# Enclosure

A 3D-printed case for the board stack this game runs on: a Waveshare RP2040-PiZero, the Waveshare
1.44" LCD HAT on top, and a PiSugar S battery board underneath. Outside, the case exposes only
the screen, the joystick and three keys, the PiSugar's USB-C charging port and its power switch.
A TPU bumper goes over the whole thing.

Assembled size: 100 x 34.5 x 35.5mm (104 x 38.5 x 39.5mm in the bumper).

## Files

`gcode/` is sliced for a Sovol SV08 (0.4mm nozzle, 0.2mm layers, no supports) in OrcaSlicer.
They use the same settings that printed the working parts. For another printer, slice the STLs in `stl/`.

| Part | STL | G-code | Material | Time |
| --- | --- | --- | --- | --- |
| Lid | `lid_1.44in_hat.stl` | `lid_pla.gcode` | PLA | ~18 min |
| Base | `base_pisugar_s.stl` | `base_pla.gcode` | PLA | ~37 min |
| Keys (and a shallow joystick) | `controls_plus*.stl` | `controls_3_sets_pla.gcode` | PLA | ~9 min |
| Joystick | `joystick_socket*.stl` | `joysticks_3_sizes_pla.gcode` | PLA | ~5 min |
| Bumper | `bumper_tpu.stl` | `bumper_tpu.gcode` | 95A TPU | ~1.5 h |
| Power switch slider and frame (untested) | `switch_*_untested.stl` | none | PLA | |

Each controls and joystick file is one size, and the G-code prints all three of each. The size is
in the file name and in the nicks on the part (1, 2 or 3):

* **Controls:** a key comb and a joystick, joined by a strip for printing. Snap the strip off. Use
  the keys; the deeper-socket joystick below replaces this one. The keys' stems are 1.5, 2.0 or
  2.5mm longer than PiSugar's originals.
* **Joystick:** socket depth 3.0, 3.5 or 4.0mm. A deeper socket sits lower on the HAT's stick, so
  it doesn't hold the stick pressed in when the lid is closed.

## Assembly

1. Put the stack in the base, battery side down, with the USB ports toward the openings.
2. Push the joystick onto the HAT's stick and lay the key comb over the keys.
3. Snap the lid on. The screen's glass rests against the lid's window lip.
4. Stretch the bumper on, starting at one rounded end.

The slider and frame are optional, and they haven't been tested. To fit them: pick the slider whose
fork grips the switch's knob (the nicks on its tab mark gaps 1.35, 1.5 and 1.65mm), push it in
through the slot from outside, then glue the frame to the case wall over its tab, gluing only the
frame's rim, with the board out.

## Credits

The shell is derived from SeedSigner's
[Orange Pill enclosure](https://github.com/SeedSigner/seedsigner/tree/dev/enclosures/orange_pill)
(MIT). The keys, the joystick and the controls' layout in the lid come from PiSugar's
[1.44" LCD cap](https://github.com/PiSugar/pisugar-case-pihat-cap/tree/master/1.44inch_lcd_cap)
(GPL-3.0).

## License

Because the controls derive from PiSugar's GPL-3.0 cap, the files in this folder (STL and
G-code) are licensed under the GNU General Public License v3.0: see `LICENSE`. The shell's
SeedSigner origin is MIT-licensed; its copyright notice is kept in `LICENSE-SeedSigner`.
