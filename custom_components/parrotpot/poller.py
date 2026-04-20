import struct
import logging
from bleak import BleakClient
from bleak_retry_connector import establish_connection, close_stale_connections
from homeassistant.components.bluetooth import async_ble_device_from_address

_LOGGER = logging.getLogger(__name__)

CHARACTERISTICS = {
    "soil_moisture": "39e1fc01-84a8-11e2-afba-0002a5d5c51b",
    "temperature":   "39e1fc02-84a8-11e2-afba-0002a5d5c51b",
    "light":         "39e1fc04-84a8-11e2-afba-0002a5d5c51b",
    "battery":       "39e1fc05-84a8-11e2-afba-0002a5d5c51b",
    "water_level":   "39e1fc07-84a8-11e2-afba-0002a5d5c51b"
}

class ParrotPotPoller:
    def __init__(self, hass, mac):
        self._hass = hass
        self._mac = mac

    async def get_data(self):
        device = async_ble_device_from_address(self._hass, self._mac, connectable=True)
        if not device:
            _LOGGER.error("Parrot Pot introuvable à l'adresse %s", self._mac)
            return None

        await close_stale_connections(device)
        results = {}

        try:
            async with await establish_connection(BleakClient, device, self._mac, timeout=15.0) as client:
                for key, uuid in CHARACTERISTICS.items():
                    try:
                        data = await client.read_gatt_char(uuid)
                        _LOGGER.debug("Lecture %s: %s", key, data.hex())
                        results[key] = self.decode(data, key)
                    except Exception as e:
                        _LOGGER.warning("Erreur lecture %s: %s", key, e)
                        results[key] = None
                return results
        except Exception as e:
            _LOGGER.error("Échec de connexion au Parrot Pot : %s", e)
            return None

    def decode(self, data, key):
        if not data or len(data) < 1:
            return None

        try:
            if key == "temperature" and len(data) >= 4:
                raw = struct.unpack_from("<I", data, 0)[0]
                return round(raw / 3276.8, 1)

            if key == "soil_moisture" and len(data) >= 2:
                raw = struct.unpack_from("<H", data, 0)[0]
                return round(raw / 100.0, 1)

            if key == "light" and len(data) >= 2:
                raw = struct.unpack_from("<H", data, 0)[0]
                return raw

            if key == "battery" and len(data) >= 4:
                raw = struct.unpack_from("<I", data, 0)[0]
                return round(raw / 65535 * 100)

            if key == "water_level" and len(data) >= 1:
                return int(data[0])

        except Exception as e:
            _LOGGER.error("Erreur décodage %s: %s", key, e)
        return None