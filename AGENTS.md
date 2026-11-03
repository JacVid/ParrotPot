# AGENTS.md — ParrotPot Home Assistant integration

Context notes for AI agents and contributors. Source: decompiled official
Parrot "Flower Power" Android app (jadx) in `parrot/` + cross-checks.
Keep this file up to date with every change.

## Repo state
- Integration: `custom_components/parrotpot/` (BLE via bleak + bleak-retry-connector)
- `parrot/` = decompiled official APK (package `com.parrot.flowerpower`). Gitignored, never commit.
- Remotes: `origin` = https://github.com/JacVid/ParrotPot.git, `denics` = https://github.com/denics/ParrotPot.git (fork, PR source)
- Active branch: `feature/app-verified-protocol`

## Model check (user's device is very old)
- App distinguishes device types via `HawaiiDevice.getDeviceType()`:
  - type == 1 → Flower Power sensor: NO tank, NO watering service, NO Plant DR
    (`LiveMode.run()` gates every tank/watering feature on `getDeviceType() != 1`)
  - type != 1 → Parrot Pot: water tank, pump, Plant DR service (39e1fd80)
- App has explicit legacy support: `SERVICES_OLD_FP_UUID`, `COMMAND_SUPPORT_OLD_DEVICES = 130`
- Evidence on user's device: `water_level` entity stuck at 0% → likely no tank
  → device is probably a Flower Power (or a Pot with empty tank). MUST verify
  empirically by checking GATT services present: watering `39e1f900` and
  Plant DR `39e1fd80`; also read firmware revision `00002a26` and device name `39e1fe03`.
- **RESOLVED (user confirmation): user's device HAS a tank → it is a Parrot Pot.**
  The permanent 0% water level came from reading the wrong characteristic
  (fc07, history bookkeeping). Correct tank level: `39e1f907` uint16 LE.
- Plan: poller probes `client.services` and exposes tank/plant-DR entities only
  when the corresponding services exist.

## Root cause of broken HA readings (from decompiled app analysis)
Current `poller.py` reads the `39e1fcXX` characteristics — a series that the
official app NEVER touches — with invented scaling:
- Temperature 515.7 °C: decodes `39e1fc02` as uint32 LE / 3276.8 — scale does
  not exist anywhere in the app → garbage.
- Battery 2.578%: decodes `39e1fc05` as uint32 / 65535 * 100 — app instead
  reads standard battery service `0000180f` char `00002a19` as a plain uint8 %.
- Light "12 lux": raw uint16 from `39e1fc04` labelled lux — app's light value
  (`39e1fa0b`) is IEEE-754 LE float32 in mol/m²/d, completely different unit.
- Moisture 26.4%: uint16 / 100 from `39e1fc01` — app uses float32 VWC from `39e1fa09`.
Fix = read live values from the live service `39e1fa00` (float32 LE,
`ByteData.getFloat`) + standard battery char.

## App-verified BLE protocol
UUID base: `xxxxxxxx-84a8-11e2-afba-0002a5d5c51b`. All multi-byte values
little-endian (`ByteData`: getFloat = LE float32; getUInt16/32 LE).

### Services
| UUID | Name | Purpose |
|---|---|---|
| 39e1fa00 | Live | live sensor values, measure period, LED |
| 39e1fb00 | Upload | history transfer (tx buffer fb01, tx status fb02) |
| 39e1fc00 | History* | NOT used by app; what current integration wrongly reads |
| 39e1fd00 | Clock | fd01 start time, fd02 UTC time (uint32 LE s) |
| 39e1fd80 | Plant DR | Pot only: status flags fd86, next watering fd87, next empty tank fd88, full tank autonomy fd89 |
| 39e1f900 | Watering | Pot only: tank level f907 (uint16), watering cmd f906 |
| 39e1fe00 | Device config | fe01 calibration, fe03 name, fe04 color, fe05 tank capacity, fe06 is_available |
| 0000180f | Battery (std) | 2a19 = battery level, uint8 % |
| 0000180a | Device info (std) | 2a25 serial, 2a26 firmware rev, 2a27 bootloader |

### Live service chars (all IEEE-754 LE float32 via ByteData.getFloat)
| Char | Meaning | Unit |
|---|---|---|
| 39e1fa09 | live soil moisture (VWC) | % |
| 39e1fa0a | live temperature | °C |
| 39e1fa0b | live light | mol/m²/d (NOT lux) |
| 39e1fa02 | soil EC | (fertilizer) |
| 39e1fa03 / fa04 | soil / air temperature (raw) | °C |
| 39e1fa06 | live measure period (uint8 s); write 1 = live on, 0 = off | s |
| 39e1fa07 | LED state | |

### Live mode flow (BleTaskHandler.startLive/stopLive)
1. Write uint8 1 → `39e1fa06`
2. Subscribe notify: `fa09`, `fa0a`, `fa0b` (+ `fd86` if not old device;
   Pot adds `fd87`, `fd88`, `fd89`, `f907`)
3. Decode: float32 LE for fa09/fa0a/fa0b; uint16 LE for f907; uint8 for fd86;
   uint32 LE seconds × 1000 for fd87/fd88 (timestamps)
4. Stop: write 0 → `fa06`, unsubscribe all

### Watering (WaterThePlant.java, POT ONLY)
Write uint16 LE value 8 (bytes `08 00`) → char `39e1f906` in service `39e1f900`.

### Plant DR status flags — char 39e1fd86 (HawaiiBleConstants)
UNREAD_ENTRIES_MASK=1, AVAILABLE_MASK=2, STARTING_MASK=4, LOW_WATER_MASK=8,
LOW_BATTERY_MASK=16, WATERING_NEEDED_MASK=32

### Clock sync (checkAndUpdateTime)
App compares `39e1fd02` (UTC s) with phone time and writes `39e1fd01` when
drifted — integration should do the same at connect.

## Change plan for this branch
1. [x] Add `denics` remote, create `feature/app-verified-protocol`
2. [x] This AGENTS.md with all findings
3. [x] `.gitignore` for `parrot/`
4. [x] translations/en.json + translations/fr.json (French strings preserved)
5. [x] Rewrite `poller.py`:
   - moisture fa09, temp fa0a, light fa0b as LE float32; battery 2a19 uint8 %
   - tank f907 uint16 LE ONLY if watering service 39e1f900 present
   - capability probe via `client.services` (has_tank / has_plant_dr)
   - DEBUG logging of raw bytes for every read (validate on real hardware)
   - drop all fc-series reads
6. [x] sensor.py: proper device classes, state_class=MEASUREMENT, light unit
   mol/m²/d (remove fake lux); conditionally create water_level entity
7. [ ] New entities (Pot only, gated on services present):
   - water Button (f906 ← `08 00`)
   - binary sensors from fd86 (low water / low battery / watering needed)
   - timestamp sensors fd87 next watering / fd88 next empty tank; duration fd89
8. [x] Clock sync at connect (fd02, ±60 s tolerance, Pot only — mirrors
   BaseTask.checkAndUpdateTime)
8b. [x] Device info (name fe03, firmware 2a26, serial 2a25) → HA device registry
8c. [x] Water Button entity (button.py, Pot only)
8d. [x] Binary sensors for Plant DR status flags fd86 (low water, low
   battery, watering needed) in binary_sensor.py, gated on has_plant_dr
8e. [x] Timestamp sensors fd87/fd88 (next watering / next empty tank) in
   sensor.py, SensorDeviceClass.TIMESTAMP, aware UTC datetime; unset
   values (>= 0xFFFFFFF0, cf. app) map to None
8f. [x] Refactor decode logic into protocol.py (pure, no HA/bleak deps)
8g. [x] Test suite in tests/ (pytest + pytest-asyncio, run via
   .venv/bin/python -m pytest; requirements-test.txt). Fake BLE client in
   tests/conftest.py stubs bleak/HA modules — 22 tests: decode units,
   status flags, epoch handling, full Parrot Pot poll, Flower Power poll,
   capability gating, clock sync, water command, connection failures
9. [ ] README: Flower Power vs Pot distinction, new entities, troubleshooting
10. [ ] Commit, push to `denics`, open PR to `origin`

## Translations — original French strings (PRESERVED)
Old poller.py log strings (code will use English per HA convention; French
kept here and in translations/fr.json):
| French (original) | English replacement |
|---|---|
| Parrot Pot introuvable à l'adresse %s | Parrot Pot not found at address %s |
| Échec de connexion au Parrot Pot : %s | Failed to connect to Parrot Pot: %s |
| Lecture %s: %s | Read %s: %s |
| Erreur lecture %s: %s | Read error %s: %s |
| Erreur décodage %s: %s | Decode error %s: %s |
Config-flow strings: title "Parrot Pot", description "Entrez l'adresse MAC de
votre Parrot Pot." / "Enter the MAC address of your Parrot Pot.", field
"Adresse MAC" / "MAC address".

## Firmware versions & OTA (from the decompiled app)

- App version: **4.6.2** (BuildConfig.java) — the last Flower Power app.
- The app bundles **no firmware binaries** (assets/ contains only FAQ JSONs).
  Firmware was fetched from Parrot's server per device via
  `FirmwareUpdateEntity` {firmware_upgrade_available, firmware_version,
  firmware_update_url}.
- API base: `https://api-flower-power-pot.parrot.com/` — **DNS dead as of
  2026-11**, so official OTA updates are permanently impossible. Devices are
  frozen on whatever firmware they currently run.
- OTA transport: TI OAD via Air Download Service `f000ffc0-0451-4000-...`
  (UUID_OAD_IMAGE_NOTIFY / UUID_OAD_IMAGE_BLOCK, 25-byte frames @ 20 ms,
  FirmwareUpdate.java).
- Version constants in the app: only **2.0.0 / 2.0.1 / 2.0.2**
  (GardenObject.FW_2_0_x). Flower Powers on those versions get a *forced*
  update dialog ("firmware_update_forcedUpdate"); versions containing "-1."
  route to UpdateFwOldSensorActivity (legacy 1.x sensors).
- Consequence for this integration: no device will EVER gain the calibrated
  fa09/fa0a/fa0b float32 characteristics via OTA again. The raw uint16
  fallback decoding (fa01/fa04/fa05 via protocol.RAW_CONVERTERS) and the
  runtime GATT capability probing are therefore essential, not optional.
- Device types (HawaiiDevice): 1 = flower-power, 2 = h2o (Parrot H2O),
  3 = pot.
- Note: the "Plant DR = firmware >= 2.0.3" claim elsewhere in this doc was an
  inference; the app itself contains no 2.0.3 literal. Plant DR presence is
  determined by our runtime probe of service 39e1fd80, which is robust.

## External protocol sources (cross-referenced)

Besides the decompiled official app (`parrot/`), two public sources were
cross-checked against it — all consistent, no contradictions:

1. **mahoutech/smart-home `docs/parrotpot-ble-api.md`** — Parrot Pot GATT map:
   confirms battery 2a19 uint8 %, calibrated live fa09/fa0a/fa0b, tank level
   f907, manual watering trigger f906; LED blink via write `1`/`0` to fa07;
   idle-disconnect after ~1 s without requests; advertised name `Parrot pot AABB`.
   Notes fa0c–fa0e (Ea/Ecb/Ec porous) exist only on Flower Power, NOT on Pot.
2. **sandeepmistry/node-flower-power PR #8 (commit 9dcb7e2)** — Parrot's
   official FlowerPower-BLE conversion polynomials for the RAW uint16
   characteristics: fa01 light (0.0864·192773.17·raw^-1.0606619 -> mol/m²/d),
   fa04 air temperature (cubic, clamp [-10,55] °C), fa05 soil moisture
   (quartic+cube chain, clamp [0,60] %). fd01 = uptime seconds (NOT wall
   clock — wall clock is fd02, which we use). fa0b confirmed as DLI.

Raw fallback implemented: poller reads calibrated fa09/fa0a/fa0b first;
if a value is missing (older firmware), it decodes the corresponding raw
characteristic (fa05/fa04/fa01) via `protocol.RAW_CONVERTERS`.

## Open questions
- Empirical validation on user's hardware via DEBUG raw-byte logs:
  which chars actually exist, what the raw values look like.
- Model confirmed Parrot Pot by user (has tank). fw revision now read at
  first poll (check DEBUG logs) — determines whether Plant DR (fd80) is
  available (requires fw >= 2.0.3).
- Later: switch coordinator to notify-based live mode for faster updates
  (watch BLE duty cycle / battery life).
- History download via fb00 upload service: format still undocumented.
