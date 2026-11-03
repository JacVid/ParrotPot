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
8. [ ] Clock sync at connect (fd01/fd02)
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

## Open questions
- Empirical validation on user's old hardware via DEBUG raw-byte logs:
  which chars actually exist, what the raw values look like.
- Confirm Flower Power vs Pot from GATT service list + firmware revision.
- Later: switch coordinator to notify-based live mode for faster updates
  (watch BLE duty cycle / battery life).
- History download via fb00 upload service: format still undocumented.
