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
