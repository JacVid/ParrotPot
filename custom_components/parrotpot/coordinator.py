from datetime import timedelta
import logging
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .poller import ParrotPotPoller

class ParrotPotCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, mac):
        super().__init__(hass, logging.getLogger(__name__), name="Parrot Pot", update_interval=timedelta(minutes=60))
        self.poller = ParrotPotPoller(hass, mac)
    async def _async_update_data(self):
        return await self.poller.get_data()