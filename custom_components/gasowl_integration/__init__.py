"""GasOwl gas levels in Home Assistant, set up in Settings > Devices & services."""

from homeassistant.const import Platform

from .const import DOMAIN
from .coordinator import GasOwlCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass, entry):
    coordinator = GasOwlCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(hass, entry, device):
    """Let the owner delete an installation's device once GasOwl no longer lists it."""
    current = {f"installation_{installation_id}" for installation_id in (entry.runtime_data.data or {})}
    return not any(
        domain == DOMAIN and identifier in current for domain, identifier in device.identifiers
    )
