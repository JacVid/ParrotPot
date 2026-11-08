from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

# key, name, device_class, icon
FLAG_SENSORS = [
    ("low_water", "Low water", None, "mdi:water-alert"),
    ("low_battery_flag", "Low battery", BinarySensorDeviceClass.BATTERY, None),
    ("watering_needed", "Watering needed", None, "mdi:watering-can-outline"),
]


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    # Plant DR status flags (39e1fd86) exist only on Parrot Pot firmware >= 2.0.3
    if coordinator.poller.has_plant_dr:
        async_add_entities(
            ParrotFlagSensor(coordinator, entry.entry_id, key, name, dc, icon)
            for key, name, dc, icon in FLAG_SENSORS
        )


class ParrotFlagSensor(CoordinatorEntity, BinarySensorEntity):
    """One bit of the Plant DR status flags characteristic (39e1fd86)."""

    def __init__(self, coordinator, entry_id, key, name, device_class, icon):
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_name = f"Pot {name}"
        self._attr_device_class = device_class
        if icon:
            self._attr_icon = icon
        self._attr_device_info = coordinator.poller.device_info()

    @property
    def is_on(self):
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._key)
