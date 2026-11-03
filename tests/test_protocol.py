"""Unit tests for the pure protocol decoding (no BLE, no HA)."""
import struct
from datetime import datetime, timezone

from custom_components.parrotpot import protocol


class TestDecodeLive:
    def test_float32_little_endian(self):
        # 21.5 °C as LE float32 = b'\x00\x00\xacA'
        assert protocol.decode_live(struct.pack("<f", 21.5), "temperature") == 21.5
        assert protocol.decode_live(struct.pack("<f", 26.4), "soil_moisture") == 26.4
        assert protocol.decode_live(struct.pack("<f", 12.34), "light") == 12.34

    def test_battery_is_plain_uint8_percent(self):
        assert protocol.decode_live(bytes([85]), "battery") == 85
        assert protocol.decode_live(bytes([100, 7, 0, 0]), "battery") == 100

    def test_short_and_empty_payloads(self):
        assert protocol.decode_live(b"", "temperature") is None
        assert protocol.decode_live(None, "temperature") is None
        assert protocol.decode_live(b"\x01\x02", "temperature") is None
        assert protocol.decode_live(b"", "battery") is None

    def test_float_rounding(self):
        assert protocol.decode_live(struct.pack("<f", 12.3456789), "light") == 12.35


class TestDecodeUint:
    def test_uint16_tank_level(self):
        assert protocol.decode_uint16(struct.pack("<H", 73)) == 73
        assert protocol.decode_uint16(struct.pack("<H", 100)) == 100
        assert protocol.decode_uint16(b"\x01") is None
        assert protocol.decode_uint16(b"") is None

    def test_uint32(self):
        assert protocol.decode_uint32(struct.pack("<I", 1700003600)) == 1700003600
        assert protocol.decode_uint32(b"\x01\x02") is None

    def test_uint8(self):
        assert protocol.decode_uint8(bytes([40])) == 40
        assert protocol.decode_uint8(b"") is None


class TestStatusFlags:
    def test_individual_bits(self):
        flags = protocol.parse_status_flags(protocol.FLAG_LOW_WATER)
        assert flags["low_water"] is True
        assert flags["low_battery_flag"] is False
        assert flags["watering_needed"] is False

    def test_combined_bits(self):
        value = protocol.FLAG_LOW_WATER | protocol.FLAG_LOW_BATTERY | protocol.FLAG_WATERING_NEEDED
        flags = protocol.parse_status_flags(value)
        assert flags["low_water"] is True
        assert flags["low_battery_flag"] is True
        assert flags["watering_needed"] is True
        assert flags["starting"] is False
        assert flags["available"] is False
        assert flags["unread_entries"] is False

    def test_none(self):
        assert protocol.parse_status_flags(None) == {}


class TestEpochToUtc:
    def test_valid_epoch(self):
        assert protocol.epoch_to_utc(1700000000) == datetime(
            2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc
        )

    def test_unset_values(self):
        assert protocol.epoch_to_utc(None) is None
        assert protocol.epoch_to_utc(0) is None
        assert protocol.epoch_to_utc(0xFFFFFFFF) is None
        assert protocol.epoch_to_utc(protocol.UNSET_UINT32) is None

    def test_result_is_aware(self):
        assert protocol.epoch_to_utc(1700000000).tzinfo == timezone.utc
