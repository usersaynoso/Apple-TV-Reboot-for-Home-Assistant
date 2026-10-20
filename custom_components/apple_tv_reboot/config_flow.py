"""Config flow: install the runtime, find an Apple TV on its pairing screen, pair with a PIN."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import callback

from .const import (
    CONF_IDENTIFIER,
    CONF_NAME,
    DISCOVER_TIMEOUT,
    DOMAIN,
    PAIR_TIMEOUT,
)
from .runtime import (
    AtvRuntimeError,
    install_runtime,
    run_helper,
    runtime_ready,
    spawn_helper,
)

_LOGGER = logging.getLogger(__name__)


async def _read_event(proc: asyncio.subprocess.Process, timeout: float) -> dict[str, Any] | None:
    """Read JSON lines from the helper until one arrives, or None when it ends/times out."""
    assert proc.stdout is not None
    try:
        async with asyncio.timeout(timeout):
            while line := await proc.stdout.readline():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict):
                    return event
    except TimeoutError:
        return None
    return None


class AppleTvRebootConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._install_task: asyncio.Task | None = None
        self._install_error = ""
        self._devices: dict[str, dict[str, Any]] = {}
        self._device: dict[str, Any] | None = None
        self._proc: asyncio.subprocess.Process | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._install_task is None and await runtime_ready(self.hass):
            return await self.async_step_discover()

        if self._install_task is None:
            self._install_task = self.hass.async_create_task(install_runtime(self.hass))
        if not self._install_task.done():
            return self.async_show_progress(
                step_id="user", progress_action="install", progress_task=self._install_task
            )
        try:
            self._install_task.result()
        except AtvRuntimeError as err:
            self._install_error = str(err)
            return self.async_show_progress_done(next_step_id="install_failed")
        return self.async_show_progress_done(next_step_id="discover")

    async def async_step_install_failed(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_abort(
            reason="install_failed", description_placeholders={"error": self._install_error}
        )

    async def async_step_discover(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        result = await run_helper(self.hass, "discover", timeout=DISCOVER_TIMEOUT)
        configured = {entry.unique_id for entry in self._async_current_entries()}
        self._devices = {
            d["identifier"]: d
            for d in result.get("devices", [])
            if d["identifier"] not in configured
        }
        if not self._devices:
            # Nothing on its pairing screen yet: show instructions, Submit scans again.
            return self.async_show_form(step_id="discover", data_schema=vol.Schema({}))
        return await self.async_step_pick()

    async def async_step_pick(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._device = self._devices[user_input[CONF_IDENTIFIER]]
            await self.async_set_unique_id(self._device["identifier"])
            self._abort_if_unique_id_configured()
            return await self._start_pairing()

        names = {ident: d["name"] for ident, d in self._devices.items()}
        return self.async_show_form(
            step_id="pick", data_schema=vol.Schema({vol.Required(CONF_IDENTIFIER): vol.In(names)})
        )

    async def _start_pairing(self) -> ConfigFlowResult:
        assert self._device is not None
        self._proc = await spawn_helper(
            self.hass, "pair", self._device["identifier"], self._device["ip"], str(self._device["port"])
        )
        event = await _read_event(self._proc, PAIR_TIMEOUT)
        if event is None or event.get("event") != "pin_required":
            self._kill_helper()
            return self.async_abort(reason="pair_failed")
        return await self.async_step_pin()

    async def async_step_pin(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._device is not None and self._proc is not None and self._proc.stdin is not None
        if user_input is None:
            return self.async_show_form(
                step_id="pin",
                data_schema=vol.Schema({vol.Required("pin"): str}),
                description_placeholders={"name": self._device["name"]},
            )

        self._proc.stdin.write(f"{user_input['pin'].strip()}\n".encode())
        await self._proc.stdin.drain()
        event = await _read_event(self._proc, PAIR_TIMEOUT)
        self._kill_helper()
        if not event or not event.get("ok"):
            _LOGGER.warning("Pairing failed: %s", (event or {}).get("error", "no result"))
            return self.async_abort(reason="pair_failed")

        return self.async_create_entry(
            title=self._device["name"],
            data={CONF_IDENTIFIER: self._device["identifier"], CONF_NAME: self._device["name"]},
        )

    def _kill_helper(self) -> None:
        if self._proc and self._proc.returncode is None:
            self._proc.kill()
        self._proc = None

    @callback
    def async_remove(self) -> None:
        """Called by Home Assistant when the flow is abandoned."""
        self._kill_helper()

