"""Write the project-local symbol library (ICs as simple boxes) and the one
project-local footprint: the hand-wound FT37-43 toroid balun.

Every other footprint comes from KiCad's stock libraries.
"""
import pathlib
import uuid

HERE = pathlib.Path(__file__).resolve().parent.parent
PITCH = 2.54


def u():
    return str(uuid.uuid4())


# ---------------------------------------------------------------- symbols ---

def sym_pin(num, name, x, y, angle):
    return (f'      (pin passive line (at {x:.2f} {y:.2f} {angle}) (length 2.54)\n'
            f'        (name "{name}" (effects (font (size 1.27 1.27))))\n'
            f'        (number "{num}" (effects (font (size 1.27 1.27)))))\n')


def box_symbol(name, ref, left, right, width=15.24, desc=""):
    """left/right: lists of (number, name) top to bottom."""
    rows = max(len(left), len(right))
    top = (rows - 1) * PITCH / 2
    h2 = top + PITCH
    w2 = width / 2
    out = [f'  (symbol "{name}" (exclude_from_sim no) (in_bom yes) (on_board yes)\n',
           f'    (property "Reference" "{ref}" (at 0 {h2 + 1.27:.2f} 0) (effects (font (size 1.27 1.27))))\n',
           f'    (property "Value" "{name}" (at 0 {-h2 - 1.27:.2f} 0) (effects (font (size 1.27 1.27))))\n',
           '    (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))\n',
           '    (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))\n',
           f'    (property "Description" "{desc}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))\n',
           f'    (symbol "{name}_0_1"\n',
           f'      (rectangle (start {-w2:.2f} {h2:.2f}) (end {w2:.2f} {-h2:.2f})\n',
           '        (stroke (width 0.254) (type default)) (fill (type background))))\n',
           f'    (symbol "{name}_1_1"\n']
    for i, (num, pname) in enumerate(left):
        out.append(sym_pin(num, pname, -w2 - 2.54, top - i * PITCH, 0))
    for i, (num, pname) in enumerate(right):
        out.append(sym_pin(num, pname, w2 + 2.54, top - i * PITCH, 180))
    out.append('    )\n  )\n')
    return "".join(out)


def write_symbols():
    ad8307 = box_symbol(
        "AD8307", "U",
        left=[("8", "INP"), ("1", "INM"), ("3", "OFS"), ("7", "INT")],
        right=[("5", "VPS"), ("6", "ENB"), ("4", "OUT"), ("2", "COM")],
        desc="AD8307 500 MHz log amplifier / RSSI detector, SOIC-8")
    lm393 = box_symbol(
        "LM393", "U",
        left=[("3", "+INA"), ("2", "-INA"), ("5", "+INB"), ("6", "-INB")],
        right=[("8", "VCC"), ("1", "OUTA"), ("7", "OUTB"), ("4", "GND")],
        desc="LM393 dual open-collector comparator, both units in one box")
    ads = box_symbol(
        "ADS1115", "U",
        left=[("4", "AIN0"), ("5", "AIN1"), ("6", "AIN2"), ("7", "AIN3"), ("1", "ADDR")],
        right=[("8", "VDD"), ("9", "SDA"), ("10", "SCL"), ("2", "ALERT/RDY"), ("3", "GND")],
        desc="ADS1115 16-bit 4-channel I2C ADC, VSSOP-10")
    eeprom = box_symbol(
        "24C32", "U",
        left=[("1", "A0"), ("2", "A1"), ("3", "A2"), ("4", "GND")],
        right=[("8", "VCC"), ("7", "WP"), ("6", "SCL"), ("5", "SDA")],
        desc="24C32 32 kbit I2C EEPROM, SOIC-8 (Pi HAT ID EEPROM)")
    amp = box_symbol(
        "LMH6624", "U",
        left=[("3", "+IN"), ("2", "-IN"), ("1", "NC"), ("5", "NC")],
        right=[("7", "V+"), ("6", "OUT"), ("4", "V-"), ("8", "NC")],
        desc="LMH6624 1.5 GHz low-noise op amp, SOIC-8")
    fet = box_symbol(
        "2N7002", "Q",
        left=[("1", "G")], right=[("3", "D"), ("2", "S")], width=7.62,
        desc="N-channel MOSFET, SOT-23 (1=G 2=S 3=D)")
    balun = box_symbol(
        "BALUN_1_9", "T",
        left=[("2", "TAP_50R")], right=[("3", "LOOP_450R"), ("1", "COM")], width=10.16,
        desc="1:9 autotransformer: 3 trifilar windings in series on an FT37-43 toroid")
    text = ('(kicad_symbol_lib (version 20241209) (generator "burst_detector_gen") '
            '(generator_version "9.0")\n' + ad8307 + lm393 + ads + eeprom + amp + fet + balun + ')\n')
    (HERE / "lapcounter_hat.kicad_sym").write_text(text)


TOROID = """(footprint "Toroid_FT37_Standing_3pad"
  (version 20241229) (generator "lapcounter_gen") (generator_version "9.0") (layer "F.Cu")
  (descr "Hand-wound 1:9 balun on an FT37-43 toroid standing on edge. Pads: 1 = COM (GND, winding A start), 2 = TAP (A end/B start, 50 ohm side), 3 = LOOP (C end, 450 ohm side). Join B end to C start in the air.")
  (property "Reference" "REF**" (at 0 -6.6 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
  (property "Value" "BALUN" (at 0 6.6 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
  (attr through_hole)
  (fp_rect (start -2.2 -5.3) (end 2.2 5.3) (stroke (width 0.12) (type solid)) (fill no) (layer "F.SilkS"))
  (fp_rect (start -1.65 -4.75) (end 1.65 4.75) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab"))
  (fp_rect (start -2.5 -5.6) (end 2.5 5.6) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd"))
  (fp_text user "1" (at -3.2 -2.54 0) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))
  (pad "1" thru_hole rect (at 0 -2.54) (size 1.6 1.6) (drill 0.9) (layers "*.Cu" "*.Mask"))
  (pad "2" thru_hole circle (at 0 0) (size 1.6 1.6) (drill 0.9) (layers "*.Cu" "*.Mask"))
  (pad "3" thru_hole circle (at 0 2.54) (size 1.6 1.6) (drill 0.9) (layers "*.Cu" "*.Mask"))
)
"""


def write_footprints():
    d = HERE / "lapcounter_hat.pretty"
    d.mkdir(exist_ok=True)
    (d / "Toroid_FT37_Standing_3pad.kicad_mod").write_text(TOROID)


if __name__ == "__main__":
    write_symbols()
    write_footprints()
    print("symbol + footprint libraries written")
