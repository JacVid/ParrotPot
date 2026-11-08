from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [ParrotIdentifyButton(coordinator, entry.entry_id)]
    if coordinator.poller.has_tank:
        entities.append(ParrotWaterButton(coordinator, entry.entry_id))
    async_add_entities(entities)


class ParrotWaterButton(CoordinatorEntity, ButtonEntity):
    """Trigger a watering cycle on the Parrot Pot.

    The official app writes uint16 LE value 8 to 39e1f906
    (WaterThePlant.java in the decompiled APK).
    """

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_water"
        self._attr_name = "Pot Water"
        self._attr_icon = "mdi:watering-can"
        self._attr_device_info = coordinator.poller.device_info()

    async def async_press(self):
        await self.coordinator.poller.water_plant()


class ParrotIdentifyButton(CoordinatorEntity, ButtonEntity):
    """Blink the notification LED to find the device.

    Writing 1 to 39e1fa07 makes the LED blink until the BLE connection
    closes (mahoutech BLE API doc).
    """

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_identify"
        self._attr_name = "Pot Identify"
        self._attr_icon = "mdi:led-on"
        self._attr_device_info = coordinator.poller.device_info()

    async def async_press(self):
        await self.coordinator.poller.set_led(True)
