from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from . import poller as poller_mod

MODES = {
    poller_mod.WATERING_MODE_MANUAL: "manual",
    poller_mod.WATERING_MODE_AUTO: "auto",
}
MODE_VALUES = {v: k for k, v in MODES.items()}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.poller.has_tank:
        async_add_entities([ParrotWateringModeSelect(coordinator, entry.entry_id)])


class ParrotWateringModeSelect(CoordinatorEntity, SelectEntity):
    """Watering mode (39e1f90d): manual or automatic (Parrot Pot only)."""

    _attr_options = ["manual", "auto"]
    _attr_icon = "mdi:auto-fix"

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_watering_mode"
        self._attr_name = "Pot Watering mode"
        self._attr_device_info = coordinator.poller.device_info()

    @property
    def current_option(self):
        if not self.coordinator.data:
            return None
        raw = self.coordinator.data.get("watering_mode")
        return MODES.get(raw)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.poller.set_watering_mode(MODE_VALUES[option])
        await self.coordinator.async_request_refresh()
