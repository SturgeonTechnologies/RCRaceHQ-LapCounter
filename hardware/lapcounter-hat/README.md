# Lap counter HAT, rev 1.1 (all-in-one RF front end)

Raspberry Pi 4 HAT (65 × 56.5 mm, M2.5 HAT holes). Everything between the
loops and the RTL-SDR v3 is on this board: loop inputs, 1:9 baluns, the
track/pad relay, a 3–8 MHz band-pass, the LMH6624 amp with a bypass relay,
the burst detector and the HAT ID EEPROM.

```
track loop -> TB1 screw terminal -> T1 1:9 balun -+- or J1 SMA (balun + coax at the loop)
pad loop   -> TB2 screw terminal -> T2 1:9 balun -+- or J5 SMA
   -> K1 (GPIO22: off = TRACK, on = PAD; the other input is grounded)
   -> TVS -> 3–8 MHz band-pass -> K2 (GPIO27: off = AMP +21 dB, on = BYPASS)
   -> splitter -+-> J2 SMA -> RTL-SDR v3 (IDs via OpenStint)
                +-> AD8307 RSSI -> ADS1115 (I2C 0x48) + LM393 -> GPIO17 + BURST LED
U5 24C32 on ID_SD/ID_SC (pins 27/28), write-protected unless JP1 is bridged.
```

Use **either** the screw terminal **or** the SMA jack on each input, not both.
- Screw terminal: loop wire or twisted pair runs straight to the board; the on-board balun does the job.
- SMA jack: the club already has a balun at the loop and coax to the table.
Put a 390 Ω resistor across the far end of each loop either way.

## Ordering (JLCPCB)
- Gerbers: `fab/lapcounter_hat_gerbers.zip` (2 layers, 1.6 mm, HASL).
- Assembly (top side): `fab/bom_jlcpcb.csv` + `fab/cpl_jlcpcb.csv`.
  Check every LCSC part is in stock and the pin-1 rotation of U1–U5 in JLC's preview.
- Fit by hand: J3 2×20 stacking header, T1/T2 (hand-wound 1:9 on FT37-43,
  8 trifilar turns), optional J4 PoE pass-through.

## Bring-up
1. Power from the Pi. `i2cdetect -y 1` shows `48`.
2. Drive GPIO22 high (`pinctrl set 22 op dh`) -> PAD LED on, relay clicks. `dl` -> back to TRACK.
3. Drive GPIO27 high -> BYPASS LED on (amp out of the path).
4. Turn RV1 until BURST goes out with the loop empty, then back off a little.
5. Transponder on the loop: BURST LED on, OpenStint decodes through J2.
6. Bridge JP1, write the HAT EEPROM (serial + UUID), then clear JP1.

## Rebuild
`source ~/tools/kicad-env.sh && JAVA=... FREEROUTING=... tools/build.sh`
regenerates everything from `tools/design.py` (single source of truth),
autoroutes with Freerouting, runs ERC/DRC (`fab/reports/`) and rewrites `fab/`.

Licensed CERN-OHL-S-2.0 (see repository `LICENSING.md`).
