"""Single source of truth for the lap counter HAT, rev 1.1.

gen_schematic.py, gen_pcb.py and gen_fab.py all read this file, so the
schematic, the board and the JLCPCB BOM can't drift apart. Coordinates are
millimetres; the board origin is the top-left corner of the HAT outline with
the 40-pin header along the top edge, x to the right, y down (same view as
the Raspberry Pi 4 mechanical drawing).

Signal chain:
  track loop -> TB1 screw terminal -> T1 1:9 balun -+- J1 SMA (pre-made balun + coax)
  pad loop   -> TB2 screw terminal -> T2 1:9 balun -+- J5 SMA
      -> K1 (GPIO22: off = TRACK, on = PAD; the unselected input is shorted to GND)
      -> TVS -> 3 MHz high-pass -> 8 MHz low-pass (50 ohm)
      -> K2 (GPIO27: off = AMP, on = BYPASS) -> LMH6624, +21 dB into 50 ohm
      -> resistive splitter -+-> J2 SMA -> RTL-SDR v3 (IDs, via OpenStint)
                             +-> AD8307 log detector -> RSSI -+-> ADS1115 AIN0 (I2C 0x48)
                                                              +-> LM393 vs RV1 -> GPIO17 + LED
  U5 24C32 on ID_SD/ID_SC (pins 27/28) = Pi HAT ID EEPROM, write-protected
  unless JP1 is bridged.
"""

PROJECT = "lapcounter_hat"
LIB = PROJECT
REV = "1.1"

# Raspberry Pi HAT outline (Pi 4 mechanical drawing / HAT spec).
BOARD_W = 65.0
BOARD_H = 56.5
CORNER_R = 3.0
HOLES = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]

# Pi 4 40-pin header: centred on x = 32.5, 3.5 mm from the top edge.
GPIO_PIN1 = (32.5 - 9.5 * 2.54, 3.5 + 1.27)       # odd row is the inner row
# Pi 4 4-pin PoE header (J14): under the top-right hole, 6.14 mm lower.
POE_CENTRE = (61.5, 3.5 + 6.14)
POE_KEEPOUT = (56.4, 6.0, 65.0, 13.4)               # x1, y1, x2, y2: no copper

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
L1206 = "Inductor_SMD:L_1206_3216Metric"
SMA = "Connector_Coaxial:SMA_BAT_Wireless_BWSMA-KWE-Z001"
TB = "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal"
SOIC8 = "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"
SOT23 = "Package_TO_SOT_SMD:SOT-23"
RELAY = "Relay_SMD:Relay_DPDT_Omron_G6K-2F-Y"
TOROID = f"{LIB}:Toroid_FT37_Standing_3pad"

# LCSC numbers, all checked in stock at JLCPCB on 2026-11-14.
LCSC_SMA = "C496551"        # BWSMA-KWE-Z001 right-angle SMA jack, through-hole
LCSC_TB = "C8465"           # WJ500V-5.08-2P screw terminal
LCSC_RELAY = "C2982926"     # Omron G6K-2F-Y 5 V DPDT signal relay
LCSC_100N = "C14663"
LCSC_10U = "C15850"
LCSC_10K = "C25804"
LCSC_100K = "C25803"
LCSC_1K = "C21190"
LCSC_49R9 = "C23185"
LCSC_LED = "C12624"
LCSC_FET = "C20917"         # AO3400A, logic-level: fully on at 3.3 V gate
LCSC_DIODE = "C81598"       # 1N4148W


def r(value, lcsc, pcb, sch):
    return dict(sym="Device:R", fp=R0603, value=value, lcsc=lcsc, pcb=pcb, sch=sch)


def c(value, lcsc, pcb, sch, fp=C0603):
    return dict(sym="Device:C", fp=fp, value=value, lcsc=lcsc, pcb=pcb, sch=sch)


# ref: symbol, footprint, value, LCSC part (None = not assembled), PCB (x, y, rot), schematic (x, y)
PARTS = {
    # --- loop inputs: screw terminal + hand-wound balun, or SMA from an external balun ---
    "J1": dict(sym="Connector:Conn_Coaxial", fp=SMA, value="TRACK (SMA)", lcsc=LCSC_SMA,
               pcb=(4.15, 12.0, 90), sch=(25.4, 50.8)),
    "TB1": dict(sym="Connector:Screw_Terminal_01x02", fp=TB, value="TRACK LOOP", lcsc=LCSC_TB,
                pcb=(5.8, 25.0, 90), sch=(25.4, 66.04)),
    "T1": dict(sym=f"{LIB}:BALUN_1_9", fp=TOROID, value="1:9 FT37-43 (hand-wound)", lcsc=None,
               pcb=(13.5, 21.0, 0), sch=(50.8, 66.04)),
    "J5": dict(sym="Connector:Conn_Coaxial", fp=SMA, value="PAD (SMA)", lcsc=LCSC_SMA,
               pcb=(4.15, 33.0, 90), sch=(25.4, 88.9)),
    "TB2": dict(sym="Connector:Screw_Terminal_01x02", fp=TB, value="PAD LOOP", lcsc=LCSC_TB,
                pcb=(5.8, 46.0, 90), sch=(25.4, 104.14)),
    "T2": dict(sym=f"{LIB}:BALUN_1_9", fp=TOROID, value="1:9 FT37-43 (hand-wound)", lcsc=None,
               pcb=(13.5, 41.0, 0), sch=(50.8, 104.14)),

    # --- K1 track/pad select -------------------------------------------------
    "K1": dict(sym="Relay:G6K-2", fp=RELAY, value="G6K-2F-Y 5V TRACK/PAD", lcsc=LCSC_RELAY,
               pcb=(23.0, 30.0, 0), sch=(88.9, 76.2)),
    "Q1": dict(sym=f"{LIB}:2N7002", fp=SOT23, value="AO3400A", lcsc=LCSC_FET,
               pcb=(20.0, 13.0, 0), sch=(88.9, 109.22)),
    "R61": r("100k", LCSC_100K, (16.5, 13.0, 90), (76.2, 116.84)),
    "D4": dict(sym="Device:D", fp="Diode_SMD:D_SOD-123", value="1N4148W", lcsc=LCSC_DIODE,
               pcb=(24.0, 16.0, 0), sch=(101.6, 101.6)),
    "D5": dict(sym="Device:LED", fp="LED_SMD:LED_0603_1608Metric", value="PAD (green)",
               lcsc=LCSC_LED, pcb=(24.0, 21.0, 180), sch=(111.76, 101.6)),
    "R62": r("1k", LCSC_1K, (24.0, 19.0, 180), (111.76, 116.84)),

    # --- protection + band-pass, 50 ohm ---------------------------------------
    "D2": dict(sym="Device:D_TVS", fp="Diode_SMD:D_SOD-323", value="PESD5V0S1BA",
               lcsc="C19224", pcb=(20.0, 38.0, 0), sch=(127.0, 88.9)),
    "C10": c("1n C0G", "C1636", (23.5, 41.0, 0), (137.16, 76.2)),
    "L10": dict(sym="Device:L", fp=L1206, value="1.5u", lcsc="C2885920",
                pcb=(26.5, 44.5, 90), sch=(147.32, 86.36)),
    "C11": c("1n C0G", "C1636", (29.5, 41.0, 0), (157.48, 76.2)),
    "C12": c("390p C0G", "C1667", (32.0, 44.5, 90), (167.64, 86.36)),
    "L11": dict(sym="Device:L", fp=L1206, value="2.2u", lcsc="C1048",
                pcb=(35.0, 41.0, 0), sch=(177.8, 76.2)),
    "C13": c("390p C0G", "C1667", (38.0, 44.5, 90), (187.96, 86.36)),

    # --- K2 amp/bypass + LMH6624 --------------------------------------------
    "K2": dict(sym="Relay:G6K-2", fp=RELAY, value="G6K-2F-Y 5V AMP/BYPASS", lcsc=LCSC_RELAY,
               pcb=(47.0, 31.0, 0), sch=(203.2, 50.8)),
    "Q2": dict(sym=f"{LIB}:2N7002", fp=SOT23, value="AO3400A", lcsc=LCSC_FET,
               pcb=(48.0, 13.0, 0), sch=(203.2, 25.4)),
    "R64": r("100k", LCSC_100K, (44.5, 13.0, 90), (190.5, 33.02)),
    "D6": dict(sym="Device:D", fp="Diode_SMD:D_SOD-123", value="1N4148W", lcsc=LCSC_DIODE,
               pcb=(52.0, 16.0, 0), sch=(215.9, 17.78)),
    "D7": dict(sym="Device:LED", fp="LED_SMD:LED_0603_1608Metric", value="BYPASS (green)",
               lcsc=LCSC_LED, pcb=(52.0, 21.0, 180), sch=(226.06, 17.78)),
    "R63": r("1k", LCSC_1K, (52.0, 19.0, 180), (226.06, 33.02)),

    "U4": dict(sym=f"{LIB}:LMH6624", fp=SOIC8, value="LMH6624MAX", lcsc="C486023",
               pcb=(36.0, 28.0, 0), sch=(152.4, 139.7)),
    "C50": c("100n", LCSC_100N, (30.5, 28.0, 90), (127.0, 132.08)),
    "R50": r("49.9", LCSC_49R9, (30.5, 32.5, 90), (127.0, 147.32)),
    "R51": r("10k", LCSC_10K, (28.0, 21.5, 90), (114.3, 160.02)),
    "R52": r("10k", LCSC_10K, (30.5, 21.5, 90), (124.46, 160.02)),
    "C51": c("10u", LCSC_10U, (33.0, 21.5, 90), (134.62, 160.02), fp=C0805),
    "R53": r("1.05k", "C22832", (35.5, 23.0, 0), (152.4, 121.92)),
    "R54": r("49.9", LCSC_49R9, (36.0, 33.0, 0), (139.7, 160.02)),
    "C53": c("10u", LCSC_10U, (39.5, 34.5, 0), (149.86, 160.02), fp=C0805),
    "C54": c("100n", LCSC_100N, (41.5, 26.0, 90), (177.8, 132.08)),
    "R55": r("49.9", LCSC_49R9, (41.5, 30.5, 90), (190.5, 132.08)),
    "R56": r("10", "C22859", (39.0, 21.5, 90), (165.1, 165.1)),
    "C55": c("10u", LCSC_10U, (41.5, 21.5, 90), (175.26, 165.1), fp=C0805),
    "C56": c("100n", LCSC_100N, (39.0, 24.4, 0), (185.42, 165.1)),

    # --- splitter: -6 dB to the SDR, -6 dB to the detector ------------------
    "J2": dict(sym="Connector:Conn_Coaxial", fp=SMA, value="TO SDR", lcsc=LCSC_SMA,
               pcb=(40.0, 52.35, 180), sch=(254.0, 63.5)),
    "R10": r("16.5", "C12054", (45.0, 41.0, 90), (228.6, 50.8)),
    "R11": r("16.5", "C12054", (45.0, 46.0, 90), (238.76, 63.5)),
    "R12": r("16.5", "C12054", (47.5, 41.0, 0), (238.76, 76.2)),
    "R13": r("52.3", "C81321", (50.5, 44.0, 90), (25.4, 139.7)),

    # --- AD8307 log detector ------------------------------------------------
    "C2": c("10n", "C1589", (52.5, 39.5, 90), (38.1, 132.08)),
    "C3": c("10n", "C1589", (52.5, 44.0, 90), (38.1, 147.32)),
    "U1": dict(sym=f"{LIB}:AD8307", fp=SOIC8, value="AD8307ARZ", lcsc="C495272",
               pcb=(57.5, 41.5, 0), sch=(63.5, 139.7)),
    "R20": r("10", "C22859", (58.0, 35.5, 0), (25.4, 175.26)),
    "C20": c("100n", LCSC_100N, (62.6, 41.5, 90), (38.1, 182.88)),
    "C21": c("10u", LCSC_10U, (54.0, 35.5, 0), (50.8, 182.88), fp=C0805),
    "C22": c("1n", "C1636", (55.0, 46.5, 0), (63.5, 160.02)),
    "C23": c("470p C0G", "C36252", (61.5, 46.0, 90), (88.9, 154.94)),

    # --- comparator, threshold, LED -----------------------------------------
    "U2": dict(sym=f"{LIB}:LM393", fp=SOIC8, value="LM393DR2G", lcsc="C7955",
               pcb=(24.0, 50.0, 0), sch=(254.0, 127.0)),
    "C30": c("100n", LCSC_100N, (19.5, 50.0, 90), (228.6, 175.26)),
    "R3": r("10k", LCSC_10K, (48.0, 49.0, 0), (228.6, 119.38)),
    "R4": r("1M", "C22935", (29.0, 48.0, 90), (276.86, 109.22)),
    "R5": r("10k", LCSC_10K, (31.0, 48.0, 90), (276.86, 121.92)),
    "R6": r("10k", LCSC_10K, (29.0, 52.5, 90), (228.6, 144.78)),
    "R7": r("10k", LCSC_10K, (31.0, 52.5, 90), (228.6, 157.48)),
    "R8": r("1k", LCSC_1K, (19.5, 54.5, 0), (276.86, 144.78)),
    "D1": dict(sym="Device:LED", fp="LED_SMD:LED_0603_1608Metric", value="BURST (green)",
               lcsc=LCSC_LED, pcb=(23.0, 54.5, 180), sch=(276.86, 157.48)),
    "RV1": dict(sym="Device:R_Potentiometer_Trim", fp="Potentiometer_SMD:Potentiometer_Bourns_TC33X_Vertical",
                value="10k THRESHOLD", lcsc="C719176", pcb=(55.0, 51.0, 0), sch=(203.2, 101.6)),
    "C31": c("100n", LCSC_100N, (50.5, 52.0, 90), (241.3, 175.26)),

    # --- ADS1115 RSSI/threshold ADC -----------------------------------------
    "U3": dict(sym=f"{LIB}:ADS1115", fp="Package_SO:MSOP-10_3x3mm_P0.5mm",
               value="ADS1115IDGSR", lcsc="C37593", pcb=(56.0, 27.0, 0), sch=(127.0, 190.5)),
    "C40": c("100n", LCSC_100N, (61.2, 27.0, 0), (254.0, 175.26)),

    # --- HAT ID EEPROM ------------------------------------------------------
    "U5": dict(sym=f"{LIB}:24C32", fp=SOIC8, value="AT24C32", lcsc="C2688466",
               pcb=(34.0, 13.5, 0), sch=(63.5, 25.4)),
    "C70": c("100n", LCSC_100N, (29.5, 13.5, 90), (38.1, 38.1)),
    "R70": r("3.9k", "C23018", (39.5, 11.5, 0), (88.9, 20.32)),
    "R71": r("3.9k", "C23018", (39.5, 13.5, 0), (88.9, 30.48)),
    "R72": r("10k", LCSC_10K, (39.5, 15.5, 0), (88.9, 40.64)),
    "JP1": dict(sym="Jumper:SolderJumper_2_Open",
                fp="Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm",
                value="WP (bridge to write)", lcsc=None, pcb=(34.0, 17.5, 0), sch=(101.6, 50.8)),

    # --- Pi header, PoE pass-through, test points ---------------------------
    "J3": dict(sym="Connector_Generic:Conn_02x20_Odd_Even",
               fp="Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical",
               value="Pi GPIO (2x20 stacking)", lcsc=None,
               pcb=(GPIO_PIN1[0], GPIO_PIN1[1], 90), sch=(330.2, 76.2)),
    "J4": dict(sym="Connector_Generic:Conn_02x02_Odd_Even",
               fp="Connector_PinHeader_2.54mm:PinHeader_2x02_P2.54mm_Vertical",
               value="PoE pass-through (not connected)", lcsc=None,
               pcb=(POE_CENTRE[0] - 1.27, POE_CENTRE[1] - 1.27, 0), sch=(330.2, 139.7)),
    "TP1": dict(sym="Connector:TestPoint", fp="TestPoint:TestPoint_Pad_D1.5mm", value="RSSI",
                lcsc=None, pcb=(60.5, 32.0, 0), sch=(304.8, 165.1)),
    "TP2": dict(sym="Connector:TestPoint", fp="TestPoint:TestPoint_Pad_D1.5mm", value="THRESH",
                lcsc=None, pcb=(33.5, 48.0, 0), sch=(314.96, 165.1)),
    "TP3": dict(sym="Connector:TestPoint", fp="TestPoint:TestPoint_Pad_D1.5mm", value="BURST",
                lcsc=None, pcb=(33.5, 51.0, 0), sch=(325.12, 165.1)),
    "TP4": dict(sym="Connector:TestPoint", fp="TestPoint:TestPoint_Pad_D1.5mm", value="GND",
                lcsc=None, pcb=(15.5, 52.0, 0), sch=(335.28, 165.1)),
    "TP5": dict(sym="Connector:TestPoint", fp="TestPoint:TestPoint_Pad_D1.5mm", value="AMP_OUT",
                lcsc=None, pcb=(42.5, 38.3, 0), sch=(345.44, 165.1)),
}

for i, (hx, hy) in enumerate(HOLES, start=1):
    PARTS[f"H{i}"] = dict(sym="Mechanical:MountingHole", fp="MountingHole:MountingHole_2.7mm_M2.5",
                          value="M2.5", lcsc=None, pcb=(hx, hy, 0), sch=(355.6 + 8.89 * i, 165.1))

GPIO_GND = ["6", "9", "14", "20", "25", "30", "34", "39"]

# net: [(ref, pad), ...]
NETS = {
    "GND": [("J3", p) for p in GPIO_GND] + [
        ("J1", "2"), ("J2", "2"), ("J5", "2"), ("TB1", "2"), ("TB2", "2"), ("T1", "1"), ("T2", "1"),
        ("K1", "6"), ("Q1", "2"), ("R61", "2"), ("Q2", "2"), ("R64", "2"),
        ("D2", "2"), ("L10", "2"), ("C12", "2"), ("C13", "2"),
        ("R52", "2"), ("C51", "2"), ("C53", "2"), ("C55", "2"), ("C56", "2"), ("U4", "4"),
        ("R13", "2"), ("C3", "2"), ("U1", "2"), ("C20", "2"), ("C21", "2"), ("C22", "2"),
        ("C23", "2"), ("U2", "4"), ("C30", "2"), ("RV1", "1"), ("R7", "2"), ("U3", "1"),
        ("U3", "3"), ("C40", "2"), ("C31", "2"), ("TP4", "1"),
        ("U5", "1"), ("U5", "2"), ("U5", "3"), ("U5", "4"), ("C70", "2"), ("JP1", "2")],
    "+5V": [("J3", "2"), ("J3", "4"), ("R20", "1"), ("U2", "8"), ("C30", "1"), ("R56", "1"),
            ("K1", "1"), ("D4", "1"), ("R62", "1"), ("K2", "1"), ("D6", "1"), ("R63", "1")],
    "+5V_A": [("R20", "2"), ("U1", "5"), ("U1", "6"), ("C20", "1"), ("C21", "1")],
    "+5V_AMP": [("R56", "2"), ("U4", "7"), ("C55", "1"), ("C56", "1"), ("R51", "1")],
    "+3V3": [("J3", "1"), ("J3", "17"), ("R5", "1"), ("R6", "1"), ("R8", "1"),
             ("RV1", "3"), ("U3", "8"), ("C40", "1"),
             ("U5", "8"), ("C70", "1"), ("R70", "1"), ("R71", "1"), ("R72", "1")],

    # inputs
    "TRK_HOT": [("TB1", "1"), ("T1", "3")],
    "TRK": [("T1", "2"), ("J1", "1"), ("K1", "2"), ("K1", "5")],
    "PAD_HOT": [("TB2", "1"), ("T2", "3")],
    "PAD": [("T2", "2"), ("J5", "1"), ("K1", "4"), ("K1", "7")],
    "RF_SEL": [("K1", "3"), ("D2", "1"), ("C10", "1")],
    "SEL_PAD": [("J3", "15"), ("Q1", "1"), ("R61", "1")],
    "K1_DRV": [("Q1", "3"), ("K1", "8"), ("D4", "2"), ("D5", "1")],
    "K1_LED": [("R62", "2"), ("D5", "2")],

    # band-pass
    "HP1": [("C10", "2"), ("L10", "1"), ("C11", "1")],
    "HP2": [("C11", "2"), ("C12", "1"), ("L11", "1")],
    "RF_FILT": [("L11", "2"), ("C13", "1"), ("K2", "3")],

    # amp / bypass
    "BYP": [("K2", "4"), ("K2", "5")],
    "AMP_IN": [("K2", "2"), ("C50", "1")],
    "AMP_P": [("C50", "2"), ("R50", "1"), ("U4", "3")],
    "VBIAS": [("R50", "2"), ("R51", "2"), ("R52", "1"), ("C51", "1")],
    "AMP_N": [("U4", "2"), ("R53", "2"), ("R54", "1")],
    "AMP_G": [("R54", "2"), ("C53", "1")],
    "AMP_O": [("U4", "6"), ("R53", "1"), ("C54", "1")],
    "AMP_OC": [("C54", "2"), ("R55", "1"), ("TP5", "1")],
    "AMP_OUT": [("R55", "2"), ("K2", "7")],
    "SPLIT_IN": [("K2", "6"), ("R10", "1")],
    "SEL_BYP": [("J3", "13"), ("Q2", "1"), ("R64", "1")],
    "K2_DRV": [("Q2", "3"), ("K2", "8"), ("D6", "2"), ("D7", "1")],
    "K2_LED": [("R63", "2"), ("D7", "2")],

    # splitter + detector
    "SPLIT": [("R10", "2"), ("R11", "1"), ("R12", "1")],
    "SDR": [("R11", "2"), ("J2", "1")],
    "RF_A": [("R12", "2"), ("R13", "1"), ("C2", "1")],
    "INP": [("C2", "2"), ("U1", "8")],
    "INM": [("C3", "1"), ("U1", "1")],
    "OFS": [("U1", "3"), ("C22", "1")],
    "RSSI": [("U1", "4"), ("C23", "1"), ("R3", "1"), ("U3", "4"), ("TP1", "1")],
    "CMP_P": [("R3", "2"), ("R4", "1"), ("U2", "3")],
    "THRESH": [("RV1", "2"), ("C31", "1"), ("U2", "2"), ("U3", "5"), ("TP2", "1")],
    "BURST": [("U2", "1"), ("R4", "2"), ("R5", "2"), ("U2", "6"), ("J3", "11"), ("TP3", "1")],
    "REF_B": [("R6", "2"), ("R7", "1"), ("U2", "5")],
    "LED_K": [("U2", "7"), ("D1", "1")],
    "LED_A": [("R8", "2"), ("D1", "2")],
    "SDA": [("U3", "9"), ("J3", "3")],
    "SCL": [("U3", "10"), ("J3", "5")],

    # HAT ID EEPROM
    "ID_SD": [("J3", "27"), ("U5", "5"), ("R70", "2")],
    "ID_SC": [("J3", "28"), ("U5", "6"), ("R71", "2")],
    "EE_WP": [("U5", "7"), ("R72", "2"), ("JP1", "1")],
}

_used_gpio = {p for n in NETS.values() for ref, p in n if ref == "J3"}
# ALERT/RDY (U3.2) is left open: the Pi polls the ADC over I2C instead.
NO_CONNECT = ([("U1", "7"), ("U3", "2"), ("U3", "6"), ("U3", "7"),
               ("U4", "1"), ("U4", "5"), ("U4", "8")]
              + [("J3", str(p)) for p in range(1, 41) if str(p) not in _used_gpio]
              + [("J4", str(p)) for p in range(1, 5)])

POWER_NETS = {"+5V", "+5V_A", "+5V_AMP"}

# Short tracks laid down before autorouting: (net, layer, [(x, y), ...]).
PRE_ROUTES = []

# Front silkscreen labels: (text, x, y[, size]).
SILK_LABELS = [
    ("TRACK", 9.0, 7.6),
    ("PAD", 9.0, 29.0),
    ("LOOP GND", 9.0, 16.0, 0.8),
    ("LOOP GND", 9.0, 37.0, 0.8),
    ("TO SDR", 40.0, 47.2),
    ("PAD", 24.0, 22.8, 0.8),
    ("BYPASS", 52.0, 22.8, 0.8),
    ("BURST", 23.0, 52.6, 0.8),
    ("THR", 55.0, 47.6, 0.8),
    ("PoE", 61.5, 14.4),
]

# Back silkscreen (mirrored), centred: CERN-OHL-S source location + serial box.
BACK_TEXT = [
    f"RC Race HQ Lap Counter HAT rev {REV}",
    "(c) 2026 Sturgeon Technologies LLC - CERN-OHL-S-2.0",
    "github.com/SturgeonTechnologies/RCRaceHQ-LapCounter-HAT",
    "SN: ____________________",
]
