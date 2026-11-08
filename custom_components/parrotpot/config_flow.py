from homeassistant import config_entries
from .const import DOMAIN
import voluptuous as vol

_HEX = set("0123456789abcdefABCDEF")

def normalize_mac(raw):
    """Validate a MAC leniently and normalize to uppercase AA:BB:CC:DD:EE:FF.

    Accepts colon- or dash-separated hex (one consistent separator), any case,
    exactly 6 octets of 2 hex digits. Returns None when invalid.
    """
    if not isinstance(raw, str) or (":" in raw and "-" in raw):
        return None
    sep = ":" if ":" in raw else "-" if "-" in raw else None
    if sep is None:
        return None
    parts = raw.split(sep)
    if len(parts) != 6 or not all(len(p) == 2 and set(p) <= _HEX for p in parts):
        return None
    return ":".join(p.upper() for p in parts)

class ParrotPotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    async def async_step_user(self, user_input=None):
        if user_input is not None:
            mac = normalize_mac(user_input.get("mac", ""))
            if mac is None:
                return self.async_show_form(step_id="user", data_schema=vol.Schema({vol.Required("mac"): str}), errors={"mac": "invalid_mac"})
            await self.async_set_unique_id(mac)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Parrot Pot", data={"mac": mac})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({vol.Required("mac"): str}))
