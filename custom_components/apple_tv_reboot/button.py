"""Restart button."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AppleTvConfigEntry
from .entity import AppleTvEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: AppleTvConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([AppleTvRestartButton(coordinator)])

    entity_platform.async_get_current_platform().async_register_entity_service(
        "restart_and_wait",
        {vol.Optional("timeout", default=300): vol.All(vol.Coerce(int), vol.Range(min=60, max=900))},
        "async_restart_and_wait",
    )


class AppleTvButton(AppleTvEntity, ButtonEntity):
    async def async_restart_and_wait(self, timeout: int) -> None:
        raise ServiceValidationError("restart_and_wait only works on the Restart button")


class AppleTvRestartButton(AppleTvButton):
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_name = "Restart"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "restart")

    async def async_press(self) -> None:
        await self.device.command("restart")

    async def async_restart_and_wait(self, timeout: int) -> None:
        await self.device.restart_and_wait(timeout)


