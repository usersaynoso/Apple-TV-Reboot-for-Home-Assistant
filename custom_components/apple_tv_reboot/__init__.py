"""Apple TV Reboot: restart and inspect an Apple TV over the network, without remote button presses."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .device import AppleTvCoordinator, AppleTvData, AppleTvDevice

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]

type AppleTvConfigEntry = ConfigEntry[AppleTvData]


async def async_setup_entry(hass: HomeAssistant, entry: AppleTvConfigEntry) -> bool:
    device = AppleTvDevice(hass, entry)
    device.coordinator = AppleTvCoordinator(hass, entry, device)
    entry.runtime_data = AppleTvData(device, device.coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # A TV that is off makes the first poll slow; do not hold up Home Assistant startup for it.
    entry.async_create_background_task(hass, device.coordinator.async_refresh(), f"{DOMAIN} first refresh")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AppleTvConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

