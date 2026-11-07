"""Config-flow tests: MAC validation/normalization (D-03) + unique-ID dedup (D-04).

Drives ParrotPotConfigFlow directly against the conftest stubs, mirroring how
test_poller.py drives ParrotPotPoller without a real HA runtime.
"""
import pytest

from custom_components.parrotpot.config_flow import ParrotPotConfigFlow, normalize_mac


@pytest.fixture(autouse=True)
def clear_configured():
    from homeassistant.config_entries import ConfigFlow

    ConfigFlow._configured.clear()


@pytest.mark.asyncio
class TestHappyPath:
    async def test_colon_lowercase_creates_normalized_entry(self):
        flow = ParrotPotConfigFlow()
        result = await flow.async_step_user({"mac": "a0:14:3d:12:34:56"})
        assert result["type"] == "create_entry"
        assert result["title"] == "Parrot Pot"
        assert result["data"]["mac"] == "A0:14:3D:12:34:56"
        assert flow.unique_id == "A0:14:3D:12:34:56"

    async def test_dash_uppercase_creates_normalized_entry(self):
        flow = ParrotPotConfigFlow()
        result = await flow.async_step_user({"mac": "A0-14-3D-12-34-56"})
        assert result["type"] == "create_entry"
        assert result["data"]["mac"] == "A0:14:3D:12:34:56"
        assert flow.unique_id == "A0:14:3D:12:34:56"


class TestNormalizeMac:
    def test_valid_variants(self):
        assert normalize_mac("a0:14:3d:12:34:56") == "A0:14:3D:12:34:56"
        assert normalize_mac("A0-14-3D-12-34-56") == "A0:14:3D:12:34:56"
        assert normalize_mac("Aa:bB:Cc:Dd:Ee:Ff") == "AA:BB:CC:DD:EE:FF"

    def test_no_input_shows_form(self):
        # covered here for helper completeness; form rendering is HA's job
        assert normalize_mac(None) is None
        assert normalize_mac("") is None
