from homeassistant.const import Platform
from homeassistant.helpers import device_registry as dr
from .coordinator import ParrotPotCoordinator
from .const import DOMAIN

async def async_setup_entry(hass, entry):
    mac = entry.data.get("mac")
    coordinator = ParrotPotCoordinator(hass, mac)
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, mac)}, name="Parrot Pot", manufacturer="Parrot")
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    return True

async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR])