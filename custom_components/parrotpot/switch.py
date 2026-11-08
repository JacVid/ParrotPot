from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.poller.has_tank:
        async_add_entities([ParrotWateringAlgorithmSwitch(coordinator, entry.entry_id)])


class ParrotWateringAlgorithmSwitch(CoordinatorEntity, SwitchEntity):
    """Automatic-watering algorithm on/off (39e1f912, Parrot Pot only)."""

    _attr_icon = "mdi:water-pump"

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_watering_algorithm"
        self._attr_name = "Pot Auto watering"
        self._attr_device_info = coordinator.poller.device_info()

    @property
    def is_on(self):
        if not self.coordinator.data:
            return None
        raw = self.coordinator.data.get("watering_algorithm_status")
        return bool(raw) if raw is not None else None

    async def async_turn_on(self, **kwargs):
        await self.coordinator.poller.set_watering_algorithm_status(1)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self.coordinator.poller.set_watering_algorithm_status(0)
        await self.coordinator.async_request_refresh()
