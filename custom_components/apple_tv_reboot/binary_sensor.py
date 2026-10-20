"""Reachable sensor."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AppleTvConfigEntry
from .entity import AppleTvEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: AppleTvConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([AppleTvReachable(entry.runtime_data.coordinator)])


class AppleTvReachable(AppleTvEntity, BinarySensorEntity):
    """True when the Apple TV answers on its remote pairing / diagnostics service.

    Checked every 5 minutes and after each restart. This is the device itself answering, so it is
    more direct than the media player state, which can read "off" or "idle" for a healthy TV.
    """

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_name = "Reachable"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "reachable")

    @property
    def is_on(self) -> bool | None:
        # None (unknown) until the first poll has finished.
        return (self.coordinator.data or {}).get("reachable")
