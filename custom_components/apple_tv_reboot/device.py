"""One paired Apple TV: serialised helper calls, status polling, restart-and-wait."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CONF_IDENTIFIER, CONF_NAME, DOMAIN, INFO_TIMEOUT, POLL_INTERVAL, RESTART_TIMEOUT
from .runtime import AtvRuntimeError, run_helper

_LOGGER = logging.getLogger(__name__)


class AppleTvDevice:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.identifier: str = entry.data[CONF_IDENTIFIER]
        self.name: str = entry.data[CONF_NAME]
        # The TV allows one tunnel at a time, so every helper call takes this lock.
        self._lock = asyncio.Lock()
        self.coordinator: AppleTvCoordinator

    @property
    def device_info(self) -> DeviceInfo:
        info = (self.coordinator.data or {}) if hasattr(self, "coordinator") else {}
        return DeviceInfo(
            identifiers={(DOMAIN, self.identifier)},
            name=self.name,
            manufacturer="Apple",
            model=info.get("product_type") or "Apple TV",
            serial_number=info.get("serial"),
            sw_version=info.get("build"),
        )

    async def call(self, command: str, timeout: float) -> dict[str, Any]:
        async with self._lock:
            try:
                return await run_helper(self.hass, command, self.identifier, timeout=timeout)
            except AtvRuntimeError as err:
                return {"ok": False, "error": str(err)}

    async def command(self, command: str) -> None:
        """Run restart/sleep and raise HomeAssistantError on failure."""
        result = await self.call(command, RESTART_TIMEOUT)
        if not result["ok"]:
            raise HomeAssistantError(f"{command.title()} failed: {result.get('error', 'unknown error')}")

    async def restart_and_wait(self, timeout: float) -> None:
        """Restart, then return once the TV has gone down and come back."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        await self.command("restart")

        # The TV acts a few seconds after the request; wait until it actually stops answering.
        went_down = False
        no_drop_deadline = loop.time() + 90
        while not went_down:
            await asyncio.sleep(5)
            if not (await self.call("info", INFO_TIMEOUT))["ok"]:
                went_down = True
            elif loop.time() > no_drop_deadline:
                raise HomeAssistantError(f"{self.name} did not go down after the restart request")

        while loop.time() < deadline:
            result = await self.call("info", INFO_TIMEOUT)
            if result["ok"]:
                await self.coordinator.async_request_refresh()
                return
            await asyncio.sleep(5)
        raise HomeAssistantError(f"{self.name} did not come back within {timeout:.0f}s")


class AppleTvCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device: AppleTvDevice) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {device.name}",
            update_interval=timedelta(seconds=POLL_INTERVAL),
        )
        self.device = device

    async def _async_update_data(self) -> dict[str, Any]:
        result = await self.device.call("info", INFO_TIMEOUT)
        previous = self.data or {}
        if result["ok"]:
            return {**result["info"], "reachable": True}
        # Unreachable is a normal state (TV off or mid-restart): keep the last readings.
        _LOGGER.debug("%s unreachable: %s", self.device.name, result.get("error"))
        return {**previous, "reachable": False}


@dataclass
class AppleTvData:
    device: AppleTvDevice
    coordinator: AppleTvCoordinator
