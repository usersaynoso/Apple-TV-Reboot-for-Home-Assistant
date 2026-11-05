"""Isolated pymobiledevice3 runtime.

pymobiledevice3 is not a manifest requirement because its declared dependencies (about 80 packages,
including IPython, FastAPI, Uvicorn and PyAV) would all be installed into Home Assistant's own
environment, and requirements cannot be installed with --no-deps. Instead the integration builds its
own virtualenv under <config>/atv_reboot with only the 30 packages that remote pairing and the
diagnostics service import, and runs atv_helper.py with that venv's Python.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from functools import partial
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN, RUNTIME_DIRNAME

_LOGGER = logging.getLogger(__name__)

COMPONENT_DIR = Path(__file__).parent
HELPER = COMPONENT_DIR / "atv_helper.py"
REQUIREMENTS = COMPONENT_DIR / "requirements-runtime.txt"
HOME_READY_KEY = f"{DOMAIN}_home_ready"


class AtvRuntimeError(Exception):
    """The runtime could not be installed or the helper failed."""


def runtime_dir(hass: HomeAssistant) -> Path:
    return Path(hass.config.path(RUNTIME_DIRNAME))


def venv_python(hass: HomeAssistant) -> Path:
    return runtime_dir(hass) / "venv" / "bin" / "python"


def _home(hass: HomeAssistant) -> Path:
    # Pairing records live under $HOME/.pymobiledevice3; keep them in /config so they survive
    # container recreation and show up in HA backups.
    return runtime_dir(hass) / "home"


def _env(hass: HomeAssistant) -> dict[str, str]:
    return {**os.environ, "HOME": str(_home(hass))}


async def _async_ensure_home(hass: HomeAssistant) -> None:
    """Create the helper's HOME once, in the executor (the first helper call does it)."""
    if hass.data.get(HOME_READY_KEY):
        return
    await hass.async_add_executor_job(partial(_home(hass).mkdir, parents=True, exist_ok=True))
    hass.data[HOME_READY_KEY] = True


async def _run(*cmd: str, env: dict[str, str] | None = None, timeout: float) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise AtvRuntimeError(f"{cmd[-1]} timed out after {timeout:.0f}s") from None
    return proc.returncode or 0, out.decode(), err.decode()


async def runtime_ready(hass: HomeAssistant) -> bool:
    python = venv_python(hass)
    if not await hass.async_add_executor_job(python.exists):
        return False
    code, _, _ = await _run(
        str(python), "-c", "import pymobiledevice3.remote.tunnel_service", env=_env(hass), timeout=60
    )
    return code == 0


async def install_runtime(hass: HomeAssistant) -> None:
    """Create the venv and install the pinned packages (about a minute)."""
    base = runtime_dir(hass)
    await hass.async_add_executor_job(partial(base.mkdir, parents=True, exist_ok=True))
    venv = base / "venv"
    steps = (
        (sys.executable, "-m", "venv", str(venv)),
        # --no-deps: pymobiledevice3 declares its whole CLI's dependencies. The list is only what
        # the helper's imports load (pairing, bonjour, the tunnel and the diagnostics service).
        (str(venv / "bin" / "pip"), "install", "--no-deps", "-q", "-r", str(REQUIREMENTS)),
    )
    for step in steps:
        code, _, err = await _run(*step, timeout=600)
        if code != 0:
            _LOGGER.error("Runtime install step %s failed: %s", step[0], err[-2000:])
            raise AtvRuntimeError(err.strip().splitlines()[-1] if err.strip() else "install failed")
    if not await runtime_ready(hass):
        raise AtvRuntimeError("pymobiledevice3 installed but cannot be imported")


def parse_result(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.strip().splitlines()):
        try:
            result = json.loads(line)
        except ValueError:
            continue
        if isinstance(result, dict) and "ok" in result:
            return result
    return {"ok": False, "error": "helper produced no result"}


async def run_helper(hass: HomeAssistant, *args: str, timeout: float) -> dict[str, Any]:
    await _async_ensure_home(hass)
    code, out, err = await _run(
        str(venv_python(hass)), str(HELPER), *args, env=_env(hass), timeout=timeout
    )
    result = parse_result(out)
    if not result["ok"] and err:
        _LOGGER.debug("Helper stderr: %s", err[-2000:])
    return result


async def spawn_helper(hass: HomeAssistant, *args: str) -> asyncio.subprocess.Process:
    """Start the helper with stdin attached (pairing needs the PIN written to it)."""
    await _async_ensure_home(hass)
    return await asyncio.create_subprocess_exec(
        str(venv_python(hass)),
        str(HELPER),
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=_env(hass),
    )
