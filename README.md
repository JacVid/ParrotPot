# Parrot Pot / Flower Power Home Assistant Integration

## Overview

This Home Assistant integration monitors **Parrot Pot** and **Parrot Flower Power** soil sensors over Bluetooth Low Energy (BLE). It reads live sensor values, exposes watering controls on Parrot Pot, and automatically adapts to the features your device and firmware actually support.

## Protocol (app-verified)

The BLE protocol was reverse-engineered from the **official Parrot Android app** (com.parrot.flowerpower 4.6.2, decompiled) and cross-checked against two independent public sources:

- [mahoutech/smart-home — parrotpot-ble-api.md](https://github.com/mahoutech/smart-home/blob/master/docs/parrotpot-ble-api.md)
- [sandeepmistry/node-flower-power PR #8](https://github.com/sandeepmistry/node-flower-power/pull/8) (Parrot's official raw-sensor conversion polynomials)

Key facts:

- Live values come from the **live service `39e1fa00`** as **little-endian IEEE-754 float32**:
  soil moisture `39e1fa09` (%), air temperature `39e1fa0a` (°C), daily light `39e1fa0b` (mol/m²/d — this is a daily light integral, *not* lux).
- Battery is the standard BLE characteristic `00002a19` (uint8 percent).
- **Firmware fallback:** older firmware that lacks the calibrated float32 characteristics gets decoded from the raw uint16 characteristics (`39e1fa01` light, `39e1fa04` temperature, `39e1fa05` moisture) using Parrot's official conversion polynomials.
- Parrot Pot only (watering service `39e1f900` present): tank level `39e1f907` (uint16 %), manual watering trigger `39e1f906` (write `8`), watering mode `39e1f90d`, auto-watering algorithm `39e1f912`.
- Plant DR predictions (service `39e1fd80` present): status flags `39e1fd86`, next watering `39e1fd87`, next empty tank `39e1fd88` (uint32 epoch seconds).
- The device's clock (`39e1fd02`) is resynchronized when it drifts more than 60 s from Home Assistant.
- The notification LED (`39e1fa07`) blinks when written `1` until the connection closes — used by the **Identify** button.

> **Note:** Parrot's cloud API (`api-flower-power-pot.parrot.com`) is gone, so no device can ever receive an official firmware update again. This integration therefore probes your device's GATT table at runtime and only creates entities for the capabilities it actually exposes.

## Features

Works on both device families; Parrot Pot-only features are created automatically when the device exposes them.

| Entity | Type | Availability |
| --- | --- | --- |
| Soil moisture | sensor (%) | all devices |
| Temperature | sensor (°C) | all devices |
| Light | sensor (mol/m²/d) | all devices |
| Battery | sensor (%) | all devices |
| Water level | sensor (%) | Parrot Pot (disabled by default otherwise) |
| Next watering | timestamp sensor | Parrot Pot w/ Plant DR |
| Next empty tank | timestamp sensor | Parrot Pot w/ Plant DR |
| Water | button (starts a watering cycle) | Parrot Pot |
| Identify | button (blinks the LED) | all devices |
| Watering mode | select (manual / auto) | Parrot Pot |
| Auto watering | switch | Parrot Pot |
| Low water / Low battery / Watering needed | binary sensors | Parrot Pot w/ Plant DR |

## Installation

### Option 1: Install via HACS (Recommended)
1. Ensure you have [HACS](https://hacs.xyz/) installed in your Home Assistant instance
2. Open HACS → Integrations
3. Click the three dots menu (⋮) in the top-right corner and select "Custom repositories"
4. Add this repository URL: `https://github.com/denics/ParrotPot`
5. Select "Integration" as the category and click Add
6. In the same Custom repositories dialog, or in HACS → Integrations → ⋮ → *Redownload* if already installed, choose the branch **`feature/app-verified-protocol`**
7. Search for "Parrot Pot" in HACS and click "Download"
8. Restart Home Assistant
9. Add the integration via Settings → Devices & Services → Add Integration → Parrot Pot (you need the MAC address of your pot)

### Option 2: Manual Installation
1. Download or `git clone -b feature/app-verified-protocol https://github.com/denics/ParrotPot`
2. Copy the `custom_components/parrotpot` folder to `/custom_components/` of your Home Assistant directory via SSH or SMB
3. Restart Home Assistant
4. Add the integration via Settings → Devices & Services → Add Integration → Parrot Pot (you need the MAC address of your pot)

## Usage
Once set up, your Parrot Pot appears as a device with the entities listed above. Values refresh every 60 minutes. On Parrot Pot you can also trigger watering, switch auto-watering on/off, and pick the watering mode.

## Testing

The decoding logic lives in dependency-free modules with a test suite (no Home Assistant installation required):

```bash
make test      # creates .venv, installs pytest + pytest-asyncio, runs 32 tests
```

## Troubleshooting
- Ensure that your Parrot Pot is not connected to your smartphone (the app holds the BLE connection; the device also disconnects after ~1 s of inactivity, which is handled by the integration).
- Values refresh every 60 minutes; force an update from the device page if needed.
- If a sensor shows *unavailable*, your firmware may not expose that characteristic — enable **debug logging** for `custom_components.parrotpot` (Settings → Devices & Services → Parrot Pot → Enable debug logging) and check which characteristics your device serves; the log prints every raw read as hex.
- Check Home Assistant logs for any other errors related to the integration.

## Development

See `AGENTS.md` for the full reverse-engineering notes: characteristic map, status flag bitmask, firmware/OTA history, and the cross-referenced protocol sources.

## Result
<img width="992" height="865" alt="image" src="https://github.com/user-attachments/assets/226e512e-5cb3-4856-bc82-957e6a847f7d" />
