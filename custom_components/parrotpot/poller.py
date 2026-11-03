"""BLE poller for Parrot Pot / Flower Power devices.

Protocol details reverse-engineered from the official Android app
(com.parrot.flowerpower, decompiled with jadx). See AGENTS.md for the
full protocol notes.

Live sensor values come from the live service 39e1fa00 as little-endian
IEEE-754 float32 (ByteData.getFloat in the app). Battery is the standard
BLE characteristic 0x2a19, a plain uint8 percent.
"""
import struct
import time
import logging
from bleak import BleakClient
from bleak_retry_connector import establish_connection, close_stale_connections
from homeassistant.components.bluetooth import async_ble_device_from_address
from .const import DOMAIN
from . import protocol

_LOGGER = logging.getLogger(__name__)

UUID_SUFFIX = "-84a8-11e2-afba-0002a5d5c51b"

# --- Services ---
SERVICE_LIVE = "39e1fa00" + UUID_SUFFIX
SERVICE_WATERING = "39e1f900" + UUID_SUFFIX
SERVICE_PLANT_DR = "39e1fd80" + UUID_SUFFIX
SERVICE_CLOCK = "39e1fd00" + UUID_SUFFIX
SERVICE_BATTERY = "0000180f-0000-1000-8000-00805f9b34fb"
SERVICE_DEVICE_INFO = "0000180a-0000-1000-8000-00805f9b34fb"

# --- Characteristics (all present on every device) ---
CHARACTERISTICS = {
    "soil_moisture": "39e1fa09" + UUID_SUFFIX,  # LE float32, %
    "temperature": "39e1fa0a" + UUID_SUFFIX,    # LE float32, °C
    "light": "39e1fa0b" + UUID_SUFFIX,          # LE float32, mol/m²/d
    "battery": "00002a19-0000-1000-8000-00805f9b34fb",  # uint8, %
}

# --- Characteristics only on Parrot Pot (watering service present) ---
CHAR_TANK_LEVEL = "39e1f907" + UUID_SUFFIX      # uint16 LE, %
CHAR_WATERING_CMD = "39e1f906" + UUID_SUFFIX    # write uint16 LE 8 = water

# --- Live service extras ---
CHAR_LED_STATE = "39e1fa07" + UUID_SUFFIX              # write 1 = blink, 0 = off

# --- Raw (uncalibrated) live characteristics, Parrot official polynomials.
# Fallback for older firmware that only exposes uint16 raw values instead of
# the calibrated float32 fa09/fa0a/fa0b. Conversions in protocol.py.
CHAR_RAW_LIGHT = "39e1fa01" + UUID_SUFFIX           # uint16 LE -> mol/m²/d
CHAR_RAW_TEMPERATURE = "39e1fa04" + UUID_SUFFIX     # uint16 LE -> °C
CHAR_RAW_SOIL_MOISTURE = "39e1fa05" + UUID_SUFFIX   # uint16 LE -> %

# --- Watering config (Parrot Pot) ---
CHAR_WATERING_MODE = "39e1f90d" + UUID_SUFFIX          # uint8: 0 = manual, 1 = auto
CHAR_WATERING_ALGORITHM_STATUS = "39e1f912" + UUID_SUFFIX  # uint8 read/write

WATERING_MODE_MANUAL = 0
WATERING_MODE_AUTO = 1

# --- Plant DR (Parrot Pot, firmware >= 2.0.3) ---
CHAR_PLANT_DR_STATUS_FLAGS = "39e1fd86" + UUID_SUFFIX    # uint8 bitmask
CHAR_PLANT_DR_NEXT_WATERING = "39e1fd87" + UUID_SUFFIX   # uint32 LE, epoch s
CHAR_PLANT_DR_NEXT_EMPTY_TANK = "39e1fd88" + UUID_SUFFIX # uint32 LE, epoch s

# --- Clock service ---
CHAR_UTC_TIME = "39e1fd02" + UUID_SUFFIX                 # uint32 LE, epoch s

# --- Device info (standard 0x180a) ---
CHAR_SERIAL_NUMBER = "00002a25-0000-1000-8000-00805f9b34fb"
CHAR_FIRMWARE_REVISION = "00002a26-0000-1000-8000-00805f9b34fb"
CHAR_DEVICE_NAME = "39e1fe03" + UUID_SUFFIX              # UTF-8

# Status flag bitmask (HawaiiBleConstants in the app)
FLAG_UNREAD_ENTRIES = 1
FLAG_AVAILABLE = 2
FLAG_STARTING = 4
FLAG_LOW_WATER = 8
FLAG_LOW_BATTERY = 16
FLAG_WATERING_NEEDED = 32


class ParrotPotPoller:
    def __init__(self, hass, mac):
        self._hass = hass
        self._mac = mac
        self.has_tank = False       # set per poll from GATT service discovery
        self.has_plant_dr = False
        self.device_name = None
        self.firmware_revision = None
        self.serial_number = None

    async def get_data(self):
        device = async_ble_device_from_address(self._hass, self._mac, connectable=True)
        if not device:
            _LOGGER.error("Parrot Pot not found at address %s", self._mac)
            return None

        await close_stale_connections(device)
        results = {}

        try:
            async with await establish_connection(
                BleakClient, device, self._mac, timeout=15.0
            ) as client:
                # Capability probe: which optional services does the device expose?
                service_uuids = {s.uuid.lower() for s in client.services}
                self.has_tank = SERVICE_WATERING in service_uuids
                self.has_plant_dr = SERVICE_PLANT_DR in service_uuids
                _LOGGER.debug(
                    "GATT services: %s (has_tank=%s, has_plant_dr=%s)",
                    sorted(service_uuids), self.has_tank, self.has_plant_dr,
                )

                # Device info (once) + clock sync, like the official app
                if not self.firmware_revision:
                    await self._read_device_info(client)
                await self._sync_clock(client)

                # Live values + battery
                for key, uuid in CHARACTERISTICS.items():
                    try:
                        data = await client.read_gatt_char(uuid)
                        _LOGGER.debug("Read %s [%s]: %s", key, uuid, data.hex())
                        results[key] = self.decode(data, key)
                    except Exception as e:
                        _LOGGER.warning("Read error %s: %s", key, e)
                        results[key] = None

                # Fallback: older firmware may only expose the raw uint16
                # characteristics (fa01/fa04/fa05). Decode with Parrot's
                # official polynomials (protocol.RAW_CONVERTERS).
                for key, raw_uuid in (
                    ("light", CHAR_RAW_LIGHT),
                    ("temperature", CHAR_RAW_TEMPERATURE),
                    ("soil_moisture", CHAR_RAW_SOIL_MOISTURE),
                ):
                    if results.get(key) is not None:
                        continue
                    try:
                        data = await client.read_gatt_char(raw_uuid)
                        _LOGGER.debug(
                            "Read raw %s [%s]: %s", key, raw_uuid, data.hex()
                        )
                        results[key] = protocol.decode_raw(data, key)
                        if results[key] is not None:
                            _LOGGER.info(
                                "%s from raw characteristic %s (calibrated "
                                "characteristic missing on this firmware)",
                                key, raw_uuid,
                            )
                    except Exception as e:
                        _LOGGER.debug("Raw fallback unavailable for %s: %s", key, e)

                # Parrot Pot only: tank level + Plant DR data
                if self.has_tank:
                    results["water_level"] = await self._read_uint16(client, CHAR_TANK_LEVEL)
                    results["watering_mode"] = await self._read_uint8(client, CHAR_WATERING_MODE)
                    results["watering_algorithm_status"] = await self._read_uint8(
                        client, CHAR_WATERING_ALGORITHM_STATUS
                    )
                else:
                    results["water_level"] = None

                if self.has_plant_dr:
                    flags = await self._read_uint8(client, CHAR_PLANT_DR_STATUS_FLAGS)
                    if flags is not None:
                        results.update(protocol.parse_status_flags(flags))
                        results["status_flags_raw"] = flags
                    results["next_watering"] = await self._read_uint32(client, CHAR_PLANT_DR_NEXT_WATERING)
                    results["next_empty_tank"] = await self._read_uint32(client, CHAR_PLANT_DR_NEXT_EMPTY_TANK)

                return results
        except Exception as e:
            _LOGGER.error("Failed to connect to Parrot Pot: %s", e)
            return None

    def decode(self, data, key):
        """Decode a characteristic value (see protocol.py)."""
        value = protocol.decode_live(data, key)
        if value is None and key in protocol.FLOAT_KEYS and data and len(data) < 4:
            _LOGGER.warning("Short payload for %s: %s", key, data.hex())
        return value

    async def _read_uint8(self, client, uuid):
        return await self._read_decoded(client, uuid, protocol.decode_uint8)

    async def _read_uint16(self, client, uuid):
        return await self._read_decoded(client, uuid, protocol.decode_uint16)

    async def _read_uint32(self, client, uuid):
        return await self._read_decoded(client, uuid, protocol.decode_uint32)

    async def _read_decoded(self, client, uuid, decoder):
        try:
            data = await client.read_gatt_char(uuid)
            _LOGGER.debug("Read [%s]: %s", uuid, data.hex())
            return decoder(data)
        except Exception as e:
            _LOGGER.warning("Read error [%s]: %s", uuid, e)
            return None

    async def water_plant(self):
        """Trigger a watering cycle (Parrot Pot only).

        The official app writes uint16 LE value 8 (bytes 08 00) to 39e1f906
        (WaterThePlant.java).
        """
        device = async_ble_device_from_address(self._hass, self._mac, connectable=True)
        if not device:
            raise ConnectionError(f"Parrot Pot not found at address {self._mac}")

        await close_stale_connections(device)
        async with await establish_connection(
            BleakClient, device, self._mac, timeout=15.0
        ) as client:
            await client.write_gatt_char(CHAR_WATERING_CMD, struct.pack("<H", 8), response=True)
            _LOGGER.info("Watering command sent to %s", self._mac)

    def device_info(self):
        """Device registry attributes gathered from the device itself."""
        info = {
            "identifiers": {(DOMAIN, self._mac)},
            "name": self.device_name or "Parrot Pot",
            "manufacturer": "Parrot",
            "model": "Parrot Pot" if self.has_tank else "Flower Power",
        }
        if self.firmware_revision:
            info["sw_version"] = self.firmware_revision
        if self.serial_number:
            info["serial_number"] = self.serial_number
        return info

    async def _read_device_info(self, client):
        """Read device name, firmware revision and serial number (0x180a)."""
        try:
            data = await client.read_gatt_char(CHAR_DEVICE_NAME)
            self.device_name = data.decode("utf-8", errors="replace").strip("\x00").strip()
        except Exception as e:
            _LOGGER.debug("Device name read failed: %s", e)
        try:
            data = await client.read_gatt_char(CHAR_FIRMWARE_REVISION)
            self.firmware_revision = data.decode("utf-8", errors="replace").strip("\x00").strip()
        except Exception as e:
            _LOGGER.debug("Firmware revision read failed: %s", e)
        try:
            data = await client.read_gatt_char(CHAR_SERIAL_NUMBER)
            self.serial_number = data.decode("utf-8", errors="replace").strip("\x00").strip()
        except Exception as e:
            _LOGGER.debug("Serial number read failed: %s", e)
        _LOGGER.debug(
            "Device info: name=%s fw=%s serial=%s",
            self.device_name, self.firmware_revision, self.serial_number,
        )

    async def _sync_clock(self, client):
        """Sync the device clock if it drifts by more than 60 s.

        Mirrors BaseTask.checkAndUpdateTime in the official app: read UTC time
        (39e1fd02) and rewrite it when |device - host| > 60 s. Only done on
        Parrot Pot devices (the app skips deviceType == 1).
        """
        if not self.has_tank:
            return
        try:
            data = await client.read_gatt_char(CHAR_UTC_TIME)
            if len(data) < 4:
                return
            device_time = struct.unpack_from("<I", data, 0)[0]
            local_time = int(time.time())
            if abs(device_time - local_time) > 60:
                await client.write_gatt_char(
                    CHAR_UTC_TIME, struct.pack("<I", local_time), response=True
                )
                _LOGGER.info(
                    "Device clock resynced: was %d, now %d", device_time, local_time
                )
            else:
                _LOGGER.debug("Device clock in sync (drift %d s)", device_time - local_time)
        except Exception as e:
            _LOGGER.debug("Clock sync failed: %s", e)

    async def set_led(self, on: bool):
        """Blink the notification LED until disconnect (write 1) or turn it off.

        The mahoutech BLE API doc documents this on the LED handler (39e1fa07).
        """
        await self._write_uint8(CHAR_LED_STATE, 1 if on else 0)

    async def set_watering_mode(self, mode: int):
        """Write watering mode (39e1f90d): 0 = manual, 1 = auto."""
        if mode not in (WATERING_MODE_MANUAL, WATERING_MODE_AUTO):
            raise ValueError(f"invalid watering mode: {mode}")
        await self._write_uint8(CHAR_WATERING_MODE, mode)

    async def set_watering_algorithm_status(self, status: int):
        """Enable/disable the watering algorithm (39e1f912), cf. the app's
        SetWateringAlgorithmStatus task."""
        await self._write_uint8(CHAR_WATERING_ALGORITHM_STATUS, status)

    async def _write_uint8(self, uuid, value):
        device = async_ble_device_from_address(self._hass, self._mac, connectable=True)
        if not device:
            raise ConnectionError(f"Parrot Pot not found at address {self._mac}")
        await close_stale_connections(device)
        async with await establish_connection(
            BleakClient, device, self._mac, timeout=15.0
        ) as client:
            await client.write_gatt_char(uuid, bytes([value]), response=True)
            _LOGGER.info("Wrote %d to %s", value, uuid)
