"""Pure protocol decoding for Parrot Pot / Flower Power BLE devices.

No Home Assistant or bleak imports — this module is unit-testable in
isolation. Values verified against the official Android app
(com.parrot.flowerpower, decompiled with jadx); see AGENTS.md.

All multi-byte values are little-endian (app's ByteData class).
"""
import struct
from datetime import datetime, timezone

# Live service (39e1fa00) keys decoded as IEEE-754 LE float32
FLOAT_KEYS = ("soil_moisture", "temperature", "light")

# Raw (uncalibrated) live characteristic UUID suffixes, used as fallback on
# older firmware that only exposes uint16 raw values. Conversion polynomials
# are Parrot's official FlowerPower-BLE API constants (node-flower-power
# sandeepmistry PR #8, commit 9dcb7e2), cross-checked against the
# decompiled Android app which names fa01 LIVE_LIGHT_SENSOR, fa04
# LIVE_AIR_TEMPERATURE and fa05 LIVE_SOIL_PERCENT_VWC.
RAW_CHAR_KEYS = {
    "39e1fa01": "light",           # raw sunlight -> mol/m²/d
    "39e1fa04": "temperature",     # raw air temperature -> °C
    "39e1fa05": "soil_moisture",   # raw soil VWC -> %
}

# Calibrated (fa09/fa0a/fa0b) -> raw fallback characteristic
CALIBRATED_TO_RAW = {
    "soil_moisture": "39e1fa05",
    "temperature": "39e1fa04",
    "light": "39e1fa01",
}

# Plant DR status flag bitmask (39e1fd86, HawaiiBleConstants)
FLAG_UNREAD_ENTRIES = 1
FLAG_AVAILABLE = 2
FLAG_STARTING = 4
FLAG_LOW_WATER = 8
FLAG_LOW_BATTERY = 16
FLAG_WATERING_NEEDED = 32

# uint32 epoch values >= 0xFFFFFFF0 mean "not set" in the firmware
# (app treats session indexes >= 4294967290 as -1)
UNSET_UINT32 = 0xFFFFFFF0


def decode_float(data):
    """Little-endian IEEE-754 float32 (ByteData.getFloat in the app)."""
    if not data or len(data) < 4:
        return None
    return round(struct.unpack_from("<f", data, 0)[0], 2)


def decode_live(data, key):
    """Decode a live/battery characteristic value.

    Live-service values (moisture fa09, temperature fa0a, light fa0b) are
    LE float32; battery is a plain uint8 percent on standard 0x2a19.
    """
    if not data or len(data) < 1:
        return None
    if key == "battery":
        return int(data[0])
    if key in FLOAT_KEYS:
        return decode_float(data)
    return None


# --- Raw uint16 conversions (Parrot official polynomials) ---
# Sources: FlowerPower-BLE API via node-flower-power (sandeepmistry PR #8);
# mahoutech/smart-home parrotpot-ble-api.md. These are the values the
# device's ADC produces before on-device calibration; older firmware may
# only expose these (fa01/fa04/fa05), so they serve as a fallback.

def convert_raw_temperature(raw):
    """Raw uint16 -> °C. Cubic polynomial, clamped to [-10, 55] (official)."""
    t = (3.044e-8 * raw ** 3
         - 8.038e-5 * raw ** 2
         + 0.1149 * raw
         - 30.449999999999999)
    return round(max(-10.0, min(55.0, t)), 2)


def convert_raw_soil_moisture(raw):
    """Raw uint16 -> VWC %. Quartic + cubic chain, clamped to [0, 60]
    (official polynomial)."""
    m = 11.4293 + (1.0698e-9 * raw ** 4
                   - 1.52538e-6 * raw ** 3
                   + 8.66976e-4 * raw ** 2
                   - 0.169422 * raw)
    m = 100.0 * (4.5e-6 * m ** 3 - 5.5e-4 * m ** 2 + 0.0292 * m - 0.053)
    return round(max(0.0, min(60.0, m)), 2)


def convert_raw_sunlight(raw):
    """Raw uint16 -> daily light in mol/m²/d (0.0864 * 192773.17 * raw^-1.0606619)."""
    if raw <= 0:
        return None
    return round(0.08640000000000001 * (192773.17000000001 * raw ** -1.0606619), 2)


RAW_CONVERTERS = {
    "temperature": convert_raw_temperature,
    "soil_moisture": convert_raw_soil_moisture,
    "light": convert_raw_sunlight,
}


def decode_raw(data, key):
    """Decode a raw uint16 characteristic via the official polynomial."""
    raw = decode_uint16(data)
    if raw is None:
        return None
    converter = RAW_CONVERTERS.get(key)
    return converter(raw) if converter else None


def decode_uint8(data):
    return int(data[0]) if data and len(data) >= 1 else None


def decode_uint16(data):
    if not data or len(data) < 2:
        return None
    return struct.unpack_from("<H", data, 0)[0]


def decode_uint32(data):
    if not data or len(data) < 4:
        return None
    return struct.unpack_from("<I", data, 0)[0]


def parse_status_flags(value):
    """Plant DR status flags bitmask -> named booleans."""
    if value is None:
        return {}
    return {
        "low_water": bool(value & FLAG_LOW_WATER),
        "low_battery_flag": bool(value & FLAG_LOW_BATTERY),
        "watering_needed": bool(value & FLAG_WATERING_NEEDED),
        "starting": bool(value & FLAG_STARTING),
        "available": bool(value & FLAG_AVAILABLE),
        "unread_entries": bool(value & FLAG_UNREAD_ENTRIES),
    }


def epoch_to_utc(raw):
    """uint32 LE epoch seconds -> aware UTC datetime, or None if unset."""
    if raw is None or raw == 0 or raw >= UNSET_UINT32:
        return None
    return datetime.fromtimestamp(raw, tz=timezone.utc)
