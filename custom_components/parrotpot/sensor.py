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
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.poller._mac)},
            "name": "Parrot Pot",
            "manufacturer": "Parrot",
        }

    @property
    def native_value(self):
        return self.coordinator.data.get(self._key) if self.coordinator.data else None
