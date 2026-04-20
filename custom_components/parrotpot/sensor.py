from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [ParrotSensor(coordinator, entry.entry_id, key) for key in ["soil_moisture", "temperature", "light", "battery", "water_level"]]
    async_add_entities(entities)

class ParrotSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry_id, key):
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_name = f"Pot {key.replace('_', ' ').capitalize()}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.poller._mac)},
            "name": "Parrot Pot",
            "manufacturer": "Parrot"
        }

        if key == "temperature":
            self._attr_device_class = "temperature"
            self._attr_native_unit_of_measurement = "°C"
        elif key == "soil_moisture":
            self._attr_device_class = "moisture"
            self._attr_native_unit_of_measurement = "%"
        elif key == "battery":
            self._attr_device_class = "battery"
            self._attr_native_unit_of_measurement = "%"
        elif key == "light":
            self._attr_native_unit_of_measurement = "lux"
        elif key == "water_level":
            self._attr_native_unit_of_measurement = "%"

    @property
    def native_value(self):
        return self.coordinator.data.get(self._key) if self.coordinator.data else None