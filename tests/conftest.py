"""Test fixtures: stub out bleak + homeassistant so the poller can be
imported and driven with a fake BLE client, without HA installed."""
import importlib.machinery
import struct
import sys
import types

import pytest


def _mod(name, package=False):
    m = types.ModuleType(name)
    m.__spec__ = importlib.machinery.ModuleSpec(name, None)
    if package:
        m.__path__ = []
    return m


def _install_stubs():
    if "bleak" not in sys.modules:
        bleak = _mod("bleak")
        bleak.BleakClient = object
        sys.modules["bleak"] = bleak

    if "bleak_retry_connector" not in sys.modules:
        brc = _mod("bleak_retry_connector")

        async def establish_connection(cls, device, address, timeout=None):
            client = brc._fake.get("client") or device
            return _FakeConnection(client)

        async def close_stale_connections(device):
            return None

        brc.establish_connection = establish_connection
        brc.close_stale_connections = close_stale_connections
        sys.modules["bleak_retry_connector"] = brc

        # stash so tests can set the client served by establish_connection
        brc._fake = {"client": None}

    if "voluptuous" not in sys.modules:
        vol_mod = _mod("voluptuous")

        class Required:
            def __init__(self, key, **kw):
                self.key = key

        class Invalid(Exception):
            pass

        class Schema:
            def __init__(self, schema):
                self.schema = schema

            def __call__(self, data):
                return data

        vol_mod.Required = Required
        vol_mod.Invalid = Invalid
        vol_mod.Schema = Schema
        sys.modules["voluptuous"] = vol_mod

    if "homeassistant" not in sys.modules:
        ha = _mod("homeassistant", package=True)
        components = _mod("homeassistant.components", package=True)
        bluetooth = _mod("homeassistant.components.bluetooth")
        bluetooth.async_ble_device_from_address = lambda hass, mac, connectable=True: object()

        const = _mod("homeassistant.const")
        class Platform:  # minimal stand-in
            SENSOR = "sensor"
            BUTTON = "button"
            BINARY_SENSOR = "binary_sensor"
        const.Platform = Platform

        helpers = _mod("homeassistant.helpers", package=True)
        update_coordinator = _mod("homeassistant.helpers.update_coordinator")
        class CoordinatorEntity:
            def __init__(self, coordinator):
                self.coordinator = coordinator
        class DataUpdateCoordinator:
            def __init__(self, *a, **k):
                pass
        class UpdateFailed(Exception):
            pass
        update_coordinator.CoordinatorEntity = CoordinatorEntity
        update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
        update_coordinator.UpdateFailed = UpdateFailed
        device_registry = _mod("homeassistant.helpers.device_registry")
        device_registry.async_get = lambda hass: None
        helpers.update_coordinator = update_coordinator
        helpers.device_registry = device_registry

        ha.components = components
        ha.const = const
        ha.helpers = helpers
        components.bluetooth = bluetooth
        sys.modules["homeassistant"] = ha
        sys.modules["homeassistant.components"] = components
        sys.modules["homeassistant.components.bluetooth"] = bluetooth
        sys.modules["homeassistant.const"] = const
        sys.modules["homeassistant.helpers"] = helpers
        sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator
        sys.modules["homeassistant.helpers.device_registry"] = device_registry

    if "homeassistant.config_entries" not in sys.modules:
        config_entries = _mod("homeassistant.config_entries")

        class AbortFlow(Exception):
            def __init__(self, reason):
                self.reason = reason

        class ConfigFlow:
            VERSION = 1
            _configured = set()  # registry of configured unique IDs (tests mutate)

            def __init_subclass__(cls, domain=None, **kwargs):
                super().__init_subclass__(**kwargs)
                cls.domain = domain

            def __init__(self):
                self.unique_id = None

            def async_show_form(self, **kw):
                return {"type": "form", **kw}

            def async_create_entry(self, **kw):
                return {"type": "create_entry", **kw}

            async def async_set_unique_id(self, uid):
                self.unique_id = uid
                return None

            def _abort_if_unique_id_configured(self):
                if self.unique_id in self._configured:
                    raise AbortFlow("already_configured")

        config_entries.ConfigFlow = ConfigFlow
        config_entries.AbortFlow = AbortFlow
        sys.modules["homeassistant"].config_entries = config_entries
        sys.modules["homeassistant.config_entries"] = config_entries


def _FakeConnection(client):
    class _CM:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *exc):
            return False

    return _CM()


_install_stubs()

sys.path.insert(0, ".")  # make custom_components importable as a package


class FakeService:
    def __init__(self, uuid):
        self.uuid = uuid


class FakeClient:
    """Fake BleakClient: canned reads, records writes."""

    def __init__(self, reads=None, services=()):
        self.reads = dict(reads or {})
        self.services = [FakeService(u) for u in services]
        self.writes = []

    async def read_gatt_char(self, uuid):
        if uuid not in self.reads:
            raise Exception(f"no such characteristic: {uuid}")
        return self.reads[uuid]

    async def write_gatt_char(self, uuid, data, response=False):
        self.writes.append((uuid, bytes(data), response))


@pytest.fixture
def fake_brc():
    import bleak_retry_connector

    return bleak_retry_connector._fake


@pytest.fixture
def pot_client():
    """Parrot Pot with full GATT: live service values, tank, Plant DR, clock."""
    from custom_components.parrotpot import poller, protocol

    epoch = 1700000000
    reads = {
        poller.CHARACTERISTICS["soil_moisture"]: struct.pack("<f", 26.4),
        poller.CHARACTERISTICS["temperature"]: struct.pack("<f", 21.5),
        poller.CHARACTERISTICS["light"]: struct.pack("<f", 12.34),
        poller.CHARACTERISTICS["battery"]: bytes([85]),
        poller.CHAR_TANK_LEVEL: struct.pack("<H", 73),
        poller.CHAR_PLANT_DR_STATUS_FLAGS: bytes(
            [protocol.FLAG_LOW_WATER | protocol.FLAG_WATERING_NEEDED]
        ),
        poller.CHAR_PLANT_DR_NEXT_WATERING: struct.pack("<I", epoch + 3600),
        poller.CHAR_PLANT_DR_NEXT_EMPTY_TANK: struct.pack("<I", epoch + 86400),
        poller.CHAR_UTC_TIME: struct.pack("<I", epoch),  # huge drift -> resync
        poller.CHAR_DEVICE_NAME: b"My Pot\x00",
        poller.CHAR_FIRMWARE_REVISION: b"2.1.0\x00",
        poller.CHAR_SERIAL_NUMBER: b"PP123456\x00",
    }
    services = (
        poller.SERVICE_LIVE,
        poller.SERVICE_WATERING,
        poller.SERVICE_PLANT_DR,
        poller.SERVICE_CLOCK,
        poller.SERVICE_BATTERY,
        poller.SERVICE_DEVICE_INFO,
    )
    return FakeClient(reads, services)


@pytest.fixture
def flower_power_client():
    """Flower Power: live service + battery only (no tank, no Plant DR)."""
    from custom_components.parrotpot import poller

    reads = {
        poller.CHARACTERISTICS["soil_moisture"]: struct.pack("<f", 15.0),
        poller.CHARACTERISTICS["temperature"]: struct.pack("<f", 18.2),
        poller.CHARACTERISTICS["light"]: struct.pack("<f", 5.5),
        poller.CHARACTERISTICS["battery"]: bytes([42]),
    }
    services = (poller.SERVICE_LIVE, poller.SERVICE_BATTERY)
    return FakeClient(reads, services)
