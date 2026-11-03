"""Integration-style tests: drive ParrotPotPoller against a fake BLE stack."""
import struct

import pytest

from conftest import FakeClient
from custom_components.parrotpot import poller as poller_mod
from custom_components.parrotpot import protocol
from custom_components.parrotpot.poller import ParrotPotPoller


@pytest.mark.asyncio
class TestGetDataParrotPot:
    async def test_full_poll(self, fake_brc, pot_client):
        fake_brc["client"] = pot_client
        p = ParrotPotPoller(hass=None, mac="AA:BB:CC:DD:EE:FF")

        data = await p.get_data()

        assert p.has_tank is True
        assert p.has_plant_dr is True
        assert data["soil_moisture"] == 26.4
        assert data["temperature"] == 21.5
        assert data["light"] == 12.34
        assert data["battery"] == 85
        assert data["water_level"] == 73
        assert data["low_water"] is True
        assert data["low_battery_flag"] is False
        assert data["watering_needed"] is True
        assert data["status_flags_raw"] == protocol.FLAG_LOW_WATER | protocol.FLAG_WATERING_NEEDED
        assert data["next_watering"] == 1700003600
        assert data["next_empty_tank"] == 1700086400

    async def test_device_info_read_once(self, fake_brc, pot_client):
        fake_brc["client"] = pot_client
        p = ParrotPotPoller(hass=None, mac="AA:BB:CC:DD:EE:FF")

        await p.get_data()
        assert p.device_name == "My Pot"
        assert p.firmware_revision == "2.1.0"
        assert p.serial_number == "PP123456"

        info = p.device_info()
        assert info["model"] == "Parrot Pot"
        assert info["sw_version"] == "2.1.0"
        assert info["serial_number"] == "PP123456"
        assert info["name"] == "My Pot"

    async def test_clock_resync_on_drift(self, fake_brc, pot_client, monkeypatch):
        fake_brc["client"] = pot_client
        monkeypatch.setattr(poller_mod.time, "time", lambda: 1700000000 + 3600)
        p = ParrotPotPoller(hass=None, mac="AA:BB:CC:DD:EE:FF")

        await p.get_data()

        assert (poller_mod.CHAR_UTC_TIME, struct.pack("<I", 1700003600), True) in pot_client.writes

    async def test_clock_not_written_when_in_sync(self, fake_brc, pot_client, monkeypatch):
        fake_brc["client"] = pot_client
        monkeypatch.setattr(poller_mod.time, "time", lambda: 1700000000 + 30)
        p = ParrotPotPoller(hass=None, mac="AA:BB:CC:DD:EE:FF")

        await p.get_data()

        assert not any(u == poller_mod.CHAR_UTC_TIME for u, _, _ in pot_client.writes)

    async def test_water_plant_writes_value_8(self, fake_brc, pot_client):
        fake_brc["client"] = pot_client
        p = ParrotPotPoller(hass=None, mac="AA:BB:CC:DD:EE:FF")

        await p.water_plant()

        assert pot_client.writes == [
            (poller_mod.CHAR_WATERING_CMD, struct.pack("<H", 8), True)
        ]


@pytest.mark.asyncio
class TestGetDataFlowerPower:
    async def test_no_tank_no_plant_dr(self, fake_brc, flower_power_client):
        fake_brc["client"] = flower_power_client
        p = ParrotPotPoller(hass=None, mac="AA:BB:CC:DD:EE:FF")

        data = await p.get_data()

        assert p.has_tank is False
        assert p.has_plant_dr is False
        assert data["water_level"] is None
        assert "low_water" not in data
        assert "next_watering" not in data
        assert data["battery"] == 42
        assert data["temperature"] == 18.2
        assert p.device_info()["model"] == "Flower Power"

    async def test_missing_char_is_none_not_fatal(self, fake_brc, flower_power_client):
        del flower_power_client.reads[poller_mod.CHARACTERISTICS["light"]]
        fake_brc["client"] = flower_power_client
        p = ParrotPotPoller(hass=None, mac="AA:BB:CC:DD:EE:FF")

        data = await p.get_data()

        assert data["light"] is None
        assert data["temperature"] == 18.2  # rest still populated


@pytest.mark.asyncio
class TestConnectionFailures:
    async def test_device_not_found(self, monkeypatch):
        # patch on the poller module: it imported the symbol into its own namespace
        monkeypatch.setattr(poller_mod, "async_ble_device_from_address", lambda *a, **k: None)
        p = ParrotPotPoller(hass=None, mac="AA:BB:CC:DD:EE:FF")
        assert await p.get_data() is None

    async def test_water_plant_device_not_found(self, monkeypatch):
        monkeypatch.setattr(poller_mod, "async_ble_device_from_address", lambda *a, **k: None)
        p = ParrotPotPoller(hass=None, mac="AA:BB:CC:DD:EE:FF")
        with pytest.raises(ConnectionError):
            await p.water_plant()


@pytest.mark.asyncio
class TestRawFallback:
    """Older firmware exposes only raw uint16 characteristics (fa01/fa04/fa05)."""

    async def test_raw_fallback_decodes_official_polynomials(self, fake_brc):
        from custom_components.parrotpot import poller, protocol

        reads = {
            poller.CHARACTERISTICS["battery"]: bytes([60]),
            # calibrated chars deliberately absent; provide raw instead
            poller.CHAR_RAW_TEMPERATURE: struct.pack("<H", 500),
            poller.CHAR_RAW_SOIL_MOISTURE: struct.pack("<H", 3000),
            poller.CHAR_RAW_LIGHT: struct.pack("<H", 1000),
            poller.CHAR_UTC_TIME: struct.pack("<I", 1700000000),
        }
        services = (poller.SERVICE_LIVE, poller.SERVICE_BATTERY, poller.SERVICE_CLOCK)
        fake_brc["client"] = FakeClient(reads, services)

        p = ParrotPotPoller(hass=None, mac="AA:BB:CC:DD:EE:FF")
        data = await p.get_data()

        assert data["temperature"] == protocol.convert_raw_temperature(500)
        assert data["soil_moisture"] == protocol.convert_raw_soil_moisture(3000)
        assert data["light"] == protocol.convert_raw_sunlight(1000)
        assert data["battery"] == 60
        assert data["water_level"] is None

    async def test_calibrated_takes_precedence_over_raw(self, fake_brc, pot_client):
        from custom_components.parrotpot import poller

        # add raw chars too — calibrated float32 must win
        pot_client.reads[poller.CHAR_RAW_TEMPERATURE] = struct.pack("<H", 500)
        pot_client.reads[poller.CHAR_RAW_LIGHT] = struct.pack("<H", 1000)
        fake_brc["client"] = pot_client

        p = ParrotPotPoller(hass=None, mac="AA:BB:CC:DD:EE:FF")
        data = await p.get_data()
        assert data["temperature"] == 21.5   # calibrated float32 value
        assert data["light"] == 12.34

    async def test_no_fallback_when_calibrated_missing_and_raw_missing(self, fake_brc):
        from custom_components.parrotpot import poller

        reads = {poller.CHARACTERISTICS["battery"]: bytes([50])}
        services = (poller.SERVICE_LIVE, poller.SERVICE_BATTERY)
        fake_brc["client"] = FakeClient(reads, services)

        p = ParrotPotPoller(hass=None, mac="AA:BB:CC:DD:EE:FF")
        data = await p.get_data()
        assert data["temperature"] is None
        assert data["soil_moisture"] is None
        assert data["light"] is None


@pytest.mark.asyncio
class TestWateringMode:
    async def test_watering_mode_read_and_select(self, fake_brc, pot_client):
        from custom_components.parrotpot import poller

        pot_client.reads[poller.CHAR_WATERING_MODE] = bytes([1])
        pot_client.reads[poller.CHAR_WATERING_ALGORITHM_STATUS] = bytes([1])
        fake_brc["client"] = pot_client
        p = ParrotPotPoller(hass=None, mac="AA:BB:CC:DD:EE:FF")

        data = await p.get_data()
        assert data["watering_mode"] == poller.WATERING_MODE_AUTO
        assert data["watering_algorithm_status"] == 1

        await p.set_watering_mode(poller.WATERING_MODE_MANUAL)
        assert (poller.CHAR_WATERING_MODE, bytes([0]), True) in pot_client.writes

        await p.set_watering_mode(poller.WATERING_MODE_AUTO)
        assert (poller.CHAR_WATERING_MODE, bytes([1]), True) in pot_client.writes

        with pytest.raises(ValueError):
            await p.set_watering_mode(7)

    async def test_set_led(self, fake_brc, pot_client):
        from custom_components.parrotpot import poller

        fake_brc["client"] = pot_client
        p = ParrotPotPoller(hass=None, mac="AA:BB:CC:DD:EE:FF")

        await p.set_led(True)
        assert (poller.CHAR_LED_STATE, bytes([1]), True) in pot_client.writes

        await p.set_led(False)
        assert (poller.CHAR_LED_STATE, bytes([0]), True) in pot_client.writes

    async def test_set_algorithm_status(self, fake_brc, pot_client):
        from custom_components.parrotpot import poller

        fake_brc["client"] = pot_client
        p = ParrotPotPoller(hass=None, mac="AA:BB:CC:DD:EE:FF")

        await p.set_watering_algorithm_status(1)
        assert (poller.CHAR_WATERING_ALGORITHM_STATUS, bytes([1]), True) in pot_client.writes

        await p.set_watering_algorithm_status(0)
        assert (poller.CHAR_WATERING_ALGORITHM_STATUS, bytes([0]), True) in pot_client.writes
