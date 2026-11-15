# Standalone race management license (design)

Status: draft for review. Nothing here is built yet.

## Decisions (Riley, 2026-11-14)

- **One-time purchase**, not yearly.
- **A board from us is required.** DIY boards (built from the public
  CERN-OHL-S files) run the public app but cannot activate Standalone.
- **Secure element (ATECC608) is a later board revision**, not v1.
- **Bundled with the board.** The license is sold with one of our boards,
  never on its own. Each rev 1.1 board leaves the bench with its license
  key already bound to its serial; the key is printed on a card in the box.
- **1 year of updates.** The owner keeps the version they have forever and
  gets every -pro release published within 12 months of activation
  (`updatesUntil`). See *Updates window* below.
- **Price: $500** for board + license, including the first year of
  updates. After that, **security fixes stay free** (Admin extends
  `updatesUntil` for that release); no paid renewal planned.
- **Board shape: piggyback HAT with a relay** (track loop / learning pad
  on one SDR), as all-in-one as practical. See *RF front end (rev 1.1)*.
- **SDR: RTL-SDR Blog v3** (direct sampling) is the supported SDR for the
  bundle. Riley's `.197` rig already runs one.
- **v1 boards (no EEPROM) activate on the Pi serial.** Admin-only, for our
  existing boards (Riley's, NCT's). See *Legacy v1 activation* below.

## What Standalone adds

The public app already runs heats and best-lap qualifying on the Pi
(`race.py`, `scoring.py`), but the event layout (classes, rounds, heats)
has to come from RC Race HQ. Standalone adds, on the Pi itself:

1. Create an event, classes and racers locally (no RC Race HQ event needed).
2. Set up qualifying rounds (count, heat size, length, best-lap or
   best-N-consecutive).
3. Generate mains from qualifying results (A/B/C mains, bump-ups optional).
4. Print/display results without an internet connection.

Not included, so hosted plans keep their value: online registration and
payments, SMS, the shared transponder library, the public event/news site.
A Standalone Pi can still be paired to a club later and keeps working.

## Keeping it out of the public repo

The public app is FSL and anyone can rebuild it, so a license check in
public code only stops honest people. Standalone therefore lives in a
**private** module:

- Repo: `SturgeonTechnologies/RCRaceHQ-LapCounter-Pro` (private).
- Image: `ghcr.io/sturgeontechnologies/rcracehq-lapcounter-pro`, built
  `FROM` the public image, adds the `lapcounter_pro` package and its screens.
- Private package. Each activated Pi gets a pull token scoped to that
  package (returned at activation, stored root-only on the Pi).
- The public app gets one small hook: if `lapcounter_pro` is importable
  *and* a valid license file is present, register its blueprint. Otherwise
  nothing changes.

## Hardware identity

Two IDs, both read at activation:

| ID | Source | Notes |
|---|---|---|
| Pi serial | `/sys/firmware/devicetree/base/serial-number` | Fixed to the SoC. Not the eth0 MAC (changeable in one command, and a USB NIC changes it). |
| Board serial + UUID | HAT ID EEPROM, exposed by Linux at `/proc/device-tree/hat/{uuid,product,vendor,custom_0}` | Written at our factory step. |

### HAT change required (rev 1.1)

The v1 schematic (breadboard gist) already includes the ID EEPROM; the
v0 KiCad board in the public HAT repo does not. Rev 1.1 lays out the
standard Raspberry Pi HAT ID circuit:

- U? `CAT24C32` (or `24AA32A`) 32 kbit I2C EEPROM, SOIC-8 (JLC basic part
  if available).
- SDA -> Pi pin 27 (`ID_SD`, GPIO0), SCL -> pin 28 (`ID_SC`, GPIO1),
  3.9 kΩ pull-ups to 3.3 V on both (per the HAT spec).
- A0-A2 to GND (address 0x50).
- WP: pulled **high** through 10 kΩ (write-protected), with a test pad /
  solder jumper to GND for the factory programming step.
- 100 nF decoupling.
- Silkscreen: `github.com/SturgeonTechnologies/RCRaceHQ-LapCounter-HAT`
  (CERN-OHL-S source location) and a serial label area.

### Factory programming step

Per board, on a jig Pi with WP jumpered low:

1. Generate a UUID and serial `RRHQ-<rev>-<6 digits>`.
2. `eepmake` with vendor `Sturgeon Technologies LLC`, product
   `RC Race HQ Lap Counter HAT`, product_id/ver for the rev, the UUID,
   and the serial in `custom_0`; `eepflash.sh -w` to the EEPROM.
3. Read back, then register `{serial, uuid, rev}` in RC Race HQ's
   **sold boards** table (Admin) with status `in_stock`.
4. Remove the jumper (WP high). Print the serial label.

DIY boards either have no EEPROM or one whose serial isn't in our table,
so activation refuses them.

## RF front end (rev 1.1)

Goal: as close to all-in-one as practical. Pi + our board + loop wire.

```
 TRACK LOOP (390 Ω at far end) ─ twisted pair ─► TB1 ┐            (or SMA J1)
                                                     ├─ 1:9 balun ┐
 LEARNING PAD (390 Ω)          ─ twisted pair ─► TB2 ┘            │ (or SMA J5)
                                                  K1 relay (GPIO22) picks one
                                                       │
                              clamp ► 3–8 MHz BPF ► LMH6624 (gain: bypass/low/high)
                                                       │
                                     ┌─────────────────┼────────────────┐
                                     ▼                 ▼                ▼
                               on-board SDR       J2 "ext SDR"     AD8307 detector
                          (RTL2832U, direct-       (SMA, v3/v4      → ADS1115 (loop
                           sampling, no tuner)      dongle)          health / RSSI)
                                     │  solder jumper selects one
                                     └── USB jumper ► Pi USB port
```

- **Inputs:** each input has a 2-screw terminal *and* an SMA jack. A 1:9
  HF transformer (OpenStint's recommended balun ratio) behind each, so
  loop wire lands on the board directly. Clubs with an existing
  balun + coax keep using the SMA jack. The 390 Ω loop termination stays
  at the far end of the loop, so it ships in the kit, not on the board.
- **Relay K1 (GPIO22):** race mode = track loop, learn mode = pad. One SDR
  can't time and learn at once (a parked car on the pad would collide with
  finish-line passes), so the app locks learning while a heat is running.
- **Gain is switchable** (jumper or GPIO): *bypass* for an RTL-SDR v4
  (OpenStint: v4 needs no amp, and too much gain overloads it), *low/high*
  for the v3 or the on-board SDR, which use direct sampling and need gain.
- **SDR:** the bundle standardises on the **v3 design**. Rev 1.1 puts a
  v3-style direct-sampling RTL2832U on the board (no tuner chip) with a
  solder jumper to fall back to an external dongle on J2 if the first spin
  doesn't work. If the on-board SDR is dropped, the kit ships a genuine
  RTL-SDR Blog v3 + SMA M–M cable instead (not a generic clone).
- **Supply risk:** RTL-SDR Blog v3 is still sold but v4 is the current
  model; the on-board SDR removes that dependency, and gain bypass keeps
  v4 dongles working.
- **Unpopulated on trial boards:** DS3231 RTC, DC jack/PoE section.

**Kit contents (trial):** board, 2× 390 Ω loop terminators, SMA M–M cable
(only if external SDR), quick-start card with license key.

**Validate before layout:** on `.197` (v3 + bare loop wire today) fit a
1:9 balun + 390 Ω termination + RG316 and compare pass rate. That tells us
how much of the earlier weak-RF trouble was the missing balun/termination
and how much gain the v3 actually wants.

## Activation

```
Pi (first setup, internet needed once)            RC Race HQ
--------------------------------------            ----------
POST /api/licenses/activate
  { licenseKey, piSerial, boardSerial, boardUuid } ->  check key exists, unused or same hardware
                                                       check board in sold-boards table, not bound elsewhere
                                                       bind key <-> board <-> Pi
                                                   <-  { licenseFile, pullToken }
write /var/lib/lapcounter/license.json (0600)
docker login ghcr.io with pullToken; pull -pro image
```

- **License key**: issued on purchase (shown in the buyer's RC Race HQ
  account and on the receipt). One key = one board.
- **License file**: JSON payload + signature.
  ```json
  {"v":1,"key":"LC-XXXX-XXXX","plan":"standalone",
   "piSerial":"10000000abcd1234","boardSerial":"RRHQ-11-000123",
   "boardUuid":"…","issued":"2026-11-14","updatesUntil":"…",
   "features":["standalone"]}
  ```
- **Signature**: ECDSA P-256 using an AWS KMS asymmetric key
  (`rcracehq-<stage>-license-signing`). The private key never leaves KMS.
  The public key is baked into the -pro image.
- **On every start**, the Pi verifies the signature and that both IDs still
  match the hardware. **No phone-home is required** after activation, so a
  track with no signal never locks anyone out.

## Updates window

- `updatesUntil` = activation date + 12 months, written into the signed
  license file.
- Every -pro image carries its release date (OCI label
  `org.opencontainers.image.created`, also baked into the code).
- On start, the -pro module compares its release date to `updatesUntil`.
  A newer image than the window allows **does not run Standalone**; it
  logs why and the Pi falls back to the public app features.
- The updater (and installer) only offers -pro tags released on or before
  `updatesUntil`, so an owner past the window simply stays on their last
  allowed version. Nothing stops working.
- Security fixes after the window: Admin can extend `updatesUntil` for a
  key (re-issues the file). Paid update renewals are not decided yet.

## Legacy v1 activation (no EEPROM)

For boards we already shipped before rev 1.1 (Riley's, NCT's):

- **Admin-only.** In Admin -> Licenses, an admin creates a key with
  `legacy: true` and the Pi's CPU serial. There is no self-service path.
- The license file has `boardSerial: null` and binds to `piSerial` only.
- **Moves are admin-only too**, because there is no board to anchor to.
- Weaker than rev 1.1 (nothing ties it to our hardware), which is why it
  stays a hand-issued exception. When the owner upgrades to a rev 1.1
  board, Admin retires the legacy key and binds a normal one.

## Moving a license

The **board is the anchor**; the Pi is replaceable.

- **New Pi, same board** (dead SD card / dead Pi): the owner clicks
  *Move to a new Pi* in their RC Race HQ account, re-activates on the new
  Pi. Limit 3 moves per year, admin can override.
- **New board** (RMA): Admin marks the old serial `retired`, binds the key
  to the replacement serial.
- Self-service moves need internet once, on the new Pi.

## What this does and doesn't stop

- Stops: copying the -pro image (it's private), running Standalone on a
  DIY board, one key on several boards, casual license-file editing.
- Doesn't fully stop: someone who clones a registered board's EEPROM onto
  another board *and* patches the -pro image to skip the Pi-serial check.
  Each serial activates once, so the clone needs the original board's
  owner to give up their own license. The ATECC608 revision (a key that
  can't be read out, challenge-response at start) closes the EEPROM-clone
  path.
- Legal backstop: the -pro module ships under a proprietary EULA, not FSL.

## Server side (RCRaceHQ)

New tables (both in the nightly backup):

- `boards`: `serial` (pk), `uuid`, `rev`, `status`
  (`in_stock|sold|bound|retired`), `licenseKey`, `soldTo`, history.
- `licenses`: `key` (pk), `ownerUserId`/`clubId`, `plan`, `boardSerial`
  (null for legacy), `piSerial`, `legacy`, `moves[]`, `issued`,
  `updatesUntil`, `status`.

New endpoints: `POST /licenses/activate` (unauthenticated, rate-limited,
key + hardware IDs), `POST /licenses/{key}/move` (owner), Admin CRUD for
boards and licenses. New AWS resources: the KMS key and a role allowed
`kms:Sign` on it only -> deploy-role permissions + `docs/aws-permissions.md`
in the same PR.

## Build order

1. HAT rev 1.1 (EEPROM, baluns + terminals, relay, switchable gain,
   on-board v3-style SDR with external fallback) + factory programming script, which also creates
   the board's bundled license key. *(Me + Riley for the order.)*
2. RCRaceHQ: boards/licenses tables, KMS key, activate endpoint, Admin pages.
3. Public app: the optional-blueprint hook (small, no license logic).
4. `RCRaceHQ-LapCounter-Pro`: license verification, local event/class
   builder, qualifying setup, mains generation.
5. Installer (`get.rcracehq.com/lapcounter`): prompt for an optional
   license key and activate.
6. Later: ATECC608 board revision.

## Open questions for Riley

1. ~~Price~~ $500 bundle, first year included (decided 2026-11-14).
2. ~~Update renewals~~ security fixes free, no paid renewal (decided 2026-11-14).
