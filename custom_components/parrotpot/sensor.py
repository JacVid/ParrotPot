from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

BASIC_KEYS = ["soil_moisture", "temperature", "light", "battery"]

SENSOR_META = {
    "soil_moisture": {
        "name": "Soil moisture",
        "device_class": SensorDeviceClass.MOISTURE,
        "unit": "%",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "temperature": {
        "name": "Temperature",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "unit": "°C",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    # Official app reports light as mol/m²/d (daily light integral), not lux
    "light": {
        "name": "Light",
        "device_class": None,
        "unit": "mol/m²/d",
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:white-balance-sunny",
    },
    "battery": {
        "name": "Battery",
        "device_class": SensorDeviceClass.BATTERY,
        "unit": "%",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    # Parrot Pot only
    "water_level": {
        "name": "Water level",
        "device_class": None,
        "unit": "%",
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:water",
    },
}


# Plant DR predictive dates (Parrot Pot, firmware >= 2.0.3):
# uint32 LE epoch seconds on 39e1fd87 / 39e1fd88
TIMESTAMP_SENSORS = {
    "next_watering": {"name": "Next watering", "icon": "mdi:calendar-clock"},
    "next_empty_tank": {"name": "Next empty tank", "icon": "mdi:calendar-remove"},
}

from . import protocol


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        ParrotSensor(coordinator, entry.entry_id, key) for key in BASIC_KEYS
    ]
    # Water level exists only on Parrot Pot (watering service 39e1f900).
    # has_tank is discovered during the first poll, so register the entity
    # unconditionally and disable it by default when the tank is absent;
    # users can enable it manually if detection is wrong.
    entities.append(
        ParrotSensor(
            coordinator,
            entry.entry_id,
            "water_level",
            enabled_default=coordinator.poller.has_tank,
        )
    )
    # Plant DR predictive timestamps (next watering / next empty tank)
    if coordinator.poller.has_plant_dr:
        entities.extend(
            ParrotTimestampSensor(coordinator, entry.entry_id, key, meta["name"], meta["icon"])
            for key, meta in TIMESTAMP_SENSORS.items()
        )
    async_add_entities(entities)


class ParrotSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry_id, key, enabled_default=True):
        super().__init__(coordinator)
        self._attr_entity_registry_enabled_default = enabled_default
        self._key = key
        meta = SENSOR_META[key]
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_name = f"Pot {meta['name']}"
        self._attr_device_class = meta["device_class"]
        self._attr_native_unit_of_measurement = meta["unit"]
        self._attr_state_class = meta.get("state_class")
        if meta.get("icon"):
            self._attr_icon = meta["icon"]
        self._attr_device_info = coordinator.poller.device_info()

    @property
    def native_value(self):
        return self.coordinator.data.get(self._key) if self.coordinator.data else None


class ParrotTimestampSensor(CoordinatorEntity, SensorEntity):
    """Plant DR predictive date (39e1fd87 next watering, 39e1fd88 next empty tank).

    The device reports uint32 LE epoch seconds; converted to a UTC datetime
    for SensorDeviceClass.TIMESTAMP.
    """

    def __init__(self, coordinator, entry_id, key, name, icon):
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_name = f"Pot {name}"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = icon
        self._attr_device_info = coordinator.poller.device_info()

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        return protocol.epoch_to_utc(self.coordinator.data.get(self._key))
