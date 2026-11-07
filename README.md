# Parrot Pot / Flower Power Home Assistant Integration

A Home Assistant custom integration for **Parrot Pot** and **Parrot Flower Power**
BLE plant sensors. It reads live sensor values over Bluetooth Low Energy, exposes
them as Home Assistant entities, and — on Parrot Pot — controls watering. The BLE
protocol was reverse-engineered from the official (now-defunct) Parrot Android app,
and this release is **hardware-validated on a real Parrot Pot**: live values were
confirmed plausible at the physical device and the Water button physically pumped water.

## Hardware validation status

This release was validated against real hardware (a Parrot Pot, indoors, 2026):

| Check | Verdict | Outcome |
| --- | --- | --- |
| VAL-01 — sensor plausibility | **PASS** | All live values eyeball-confirmed plausible at the device: soil moisture ≈ 5.8 % (dry soil), temperature ≈ 21.7 °C (room temperature), light ≈ 0.1 mol/m²/d (dim indoor location), battery 100 %. Raw-byte DEBUG evidence from the validation polls is retained in the project records. |
| VAL-02 — watering | **PASS** | The Water button physically pumped water on the device. |
| VAL-03 — clock sync | **documented** | The device clock was observed in sync (drift within ±1 s) on two poll cycles; no clock write was ever triggered. |

The decoding and polling logic behind this is covered by the test suite (see
[Testing](#testing) — 43 tests). See [Known limitations](#known-limitations) for
the one hardware quirk found during validation.

## Protocol (app-verified)

The BLE protocol was reverse-engineered from the **official Parrot Android app**
(com.parrot.flowerpower 4.6.2, decompiled) and cross-checked against two independent
public sources:

- [mahoutech/smart-home — parrotpot-ble-api.md](https://github.com/mahoutech/smart-home/blob/master/docs/parrotpot-ble-api.md)
- [sandeepmistry/node-flower-power PR #8](https://github.com/sandeepmistry/node-flower-power/pull/8) (Parrot's official raw-sensor conversion polynomials)

Key facts:

- Live values come from the **live service `39e1fa00`** as **little-endian IEEE-754
  float32**: soil moisture `39e1fa09` (%), temperature `39e1fa0a` (°C), daily light
  `39e1fa0b` (mol/m²/d — this is a daily light integral, *not* lux).
- Battery is the standard BLE characteristic `00002a19` (uint8 percent).
- **Firmware fallback:** older firmware that lacks the calibrated float32
  characteristics is decoded from the raw uint16 characteristics (`39e1fa01` light,
  `39e1fa04` temperature, `39e1fa05` moisture) using Parrot's official conversion
  polynomials.
- Parrot Pot only (watering service `39e1f900` present): tank level `39e1f907`
  (uint16 %), manual watering trigger `39e1f906` (write `8`), watering mode
  `39e1f90d`, auto-watering algorithm `39e1f912`.
- Plant DR predictions (service `39e1fd80` present): status flags `39e1fd86`,
  next watering `39e1fd87`, next empty tank `39e1fd88` (uint32 epoch seconds).
- The device's clock (`39e1fd02`) is resynchronized when it drifts more than 60 s
  from Home Assistant.
- The notification LED (`39e1fa07`) blinks when written `1` until the connection
  closes — used by the **Identify** button.

> **Note:** Parrot's cloud API (`api-flower-power-pot.parrot.com`) is gone, so no
> device can ever receive an official firmware update again. This integration
> therefore probes your device's GATT table at runtime and only creates entities
> for the capabilities it actually exposes.

## Features

### Flower Power vs Parrot Pot — runtime capability probing

The integration works with **both** device families and requires no configuration
to tell them apart. On every poll it inspects the device's GATT service table:

- **Watering service `39e1f900` present** → the device is a Parrot Pot (has a water
  tank and pump) — the tank/watering entities are created.
- **Plant DR service `39e1fd80` present** → the device runs the predictive "Plant DR"
  firmware — the status-flag and prediction entities are created.

A Flower Power sensor exposes neither service, so it gets exactly the core sensors
and nothing else. There is no config option to select a model — capability probing
at runtime is the single source of truth.

### Entity inventory

Entity names below are shown as they appear in Home Assistant (prefixed `Pot `).

| Entity | Type | Availability |
| --- | --- | --- |
| Pot Soil moisture | sensor (%) | all devices |
| Pot Temperature | sensor (°C) | all devices |
| Pot Light | sensor (mol/m²/d — daily light integral, not lux) | all devices |
| Pot Battery | sensor (%) | all devices |
| Pot Water level | sensor (%) — see [Known limitations](#known-limitations) (GAP-01) | Parrot Pot (registered unconditionally, disabled by default when no tank is detected) |
| Pot Next watering | timestamp sensor | Parrot Pot with Plant DR |
| Pot Next empty tank | timestamp sensor | Parrot Pot with Plant DR |
| Pot Water | button (starts a watering cycle) | Parrot Pot |
| Pot Identify | button (blinks the notification LED) | all devices |
| Pot Watering mode | select (manual / auto) | Parrot Pot |
| Pot Auto watering | switch (automatic-watering algorithm on/off) | Parrot Pot |
| Pot Low water / Pot Low battery / Pot Watering needed | binary sensors (Plant DR status flags) | Parrot Pot with Plant DR |

## Known limitations

- **GAP-01 — Water level shows `unavailable` on the validated device.**
  On the hardware used for validation, the tank-level characteristic `39e1f907`
  returns a single byte even though the tank is full, and the decoder correctly
  rejects payloads shorter than two bytes. The result: the *Pot Water level*
  sensor shows *unavailable* instead of a percentage. This is a known, tracked
  defect (candidate causes: a firmware short-payload quirk for `f907`, or a
  missing precondition before the characteristic carries a uint16); a fix is
  planned for a follow-up release. All other sensors are unaffected.
- **OBS-01 — Values refresh every 60 minutes.** The coordinator polls on a
  60-minute cadence, so a fresh install shows the installation-time readings
  until the next poll. You can force an immediate update from the device page
  (the entity's *Update* action / `homeassistant.update_entity`). A shorter
  interval or a notify-based live mode is deferred to a later release.

## Installation

### Manual installation

1. Copy the `custom_components/parrotpot` folder into the `custom_components/`
   directory of your Home Assistant config directory, e.g.
   `/Volumes/config/custom_components/parrotpot/` (via SSH, SMB or Samba).
2. Perform a **full Home Assistant restart** — a reload does not pick up new
   custom components.
3. Go to Settings → Devices & Services → Add Integration → **Parrot Pot** and
   enter the MAC address of your device.

### Installation via HACS

1. In HACS → Integrations → ⋮ → *Custom repositories*, add
   `https://github.com/denics/ParrotPot` with category *Integration*.
2. Search for "Parrot Pot" and click *Download* (the repository tracks `main`;
   no special branch step is needed).
3. Restart Home Assistant, then add the integration as in step 3 above.

## Usage

Once set up, your device appears with the entities listed above. Values refresh
every 60 minutes (see OBS-01 in [Known limitations](#known-limitations)). On a
Parrot Pot you can:

- press **Pot Water** to start a watering cycle,
- toggle **Pot Auto watering** to enable/disable the automatic-watering algorithm,
- pick **Pot Watering mode** — `manual` or `auto`.

## Testing

The decoding logic lives in dependency-free modules with a test suite of
43 tests (no Home Assistant installation required):

```bash
make test      # creates .venv, installs pytest + pytest-asyncio, runs 43 tests
```

## Troubleshooting

- **Connection problems:** make sure your Parrot Pot is not connected to your
  smartphone — the official app holds the BLE connection, and the device allows
  only one client at a time. The device also idle-disconnects after ~1 s without
  requests, which the integration handles automatically.
- **New entities or code changes not appearing:** a **full restart** of Home
  Assistant is required; reload is not enough for custom components.
- **A sensor shows *unavailable*:** your firmware may not expose that
  characteristic (for *Pot Water level*, see GAP-01 above). Enable **debug
  logging** for `custom_components.parrotpot` (Settings → Devices & Services →
  Parrot Pot → Enable debug logging) — every raw GATT read is printed as hex —
  and check which characteristics your device actually serves.
- Check the Home Assistant logs for any other errors related to the integration.

## Development

See `AGENTS.md` for the full reverse-engineering notes: characteristic map,
status flag bitmasks, firmware/OTA history, hardware-validation clock
observations, and the cross-referenced protocol sources.

## Result

The integration working in Home Assistant:

<img width="992" height="865" alt="image" src="https://github.com/user-attachments/assets/226e512e-5cb3-4856-bc82-957e6a847f7d" />
