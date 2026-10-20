"""Pair with and restart a tvOS device. Runs inside the isolated pymobiledevice3 venv.

Home Assistant itself never imports this file: runtime.py runs it with the venv's Python.
Every line printed to stdout is a JSON object; the last one is {"ok": true, ...} or
{"ok": false, "error": "..."}.
"""

import argparse
import asyncio
import builtins
import json
import logging
import plistlib
import sys
import traceback
from contextlib import asynccontextmanager


def emit(**payload) -> None:
    print(json.dumps(payload), flush=True)


async def discover() -> dict:
    from pymobiledevice3.bonjour import browse_remotepairing_manual_pairing

    devices: dict[str, dict] = {}
    for answer in await browse_remotepairing_manual_pairing(timeout=8):
        identifier = answer.properties["identifier"]
        addresses = [a.full_ip for a in answer.addresses]
        # Prefer IPv4: link-local IPv6 needs a scope id that differs between hosts.
        ip = next((a for a in addresses if ":" not in a), addresses[0] if addresses else None)
        if ip is None:
            continue
        devices.setdefault(
            identifier,
            {"identifier": identifier, "name": answer.properties["name"], "ip": ip, "port": answer.port},
        )
    return {"ok": True, "devices": list(devices.values())}


async def pair(identifier: str, ip: str, port: int) -> dict:
    from pymobiledevice3.common import get_home_folder
    from pymobiledevice3.exceptions import RemotePairingCompletedError
    from pymobiledevice3.pair_records import (
        PAIRING_RECORD_EXT,
        generate_host_id,
        get_remote_pairing_record_filename,
    )
    from pymobiledevice3.remote.tunnel_service import RemotePairingManualPairingService

    def read_pin(_prompt: str = "") -> str:
        emit(event="pin_required")
        return sys.stdin.readline().strip()

    builtins.input = read_pin

    async with RemotePairingManualPairingService(identifier, ip, port) as service:
        try:
            await service.connect(autopair=True)
        except RemotePairingCompletedError:
            # The device closes the connection when pairing is done; the record is already saved.
            pass

    # The pair-verify signature includes an identifier derived from this machine's hostname, and
    # the record does not store it. Pin it so the record keeps working if the hostname changes.
    path = get_home_folder() / f"{get_remote_pairing_record_filename(identifier)}.{PAIRING_RECORD_EXT}"
    record = plistlib.loads(path.read_bytes())
    record.setdefault("host_identifier", generate_host_id())
    path.write_bytes(plistlib.dumps(record))
    return {"ok": True}


class NotReachable(Exception):
    """The Apple TV was not found, or it rejected the pairing."""


@asynccontextmanager
async def diagnostics_session(identifier: str):
    """Open a tunnel to the Apple TV and yield (rsd, diagnostics service)."""
    from pymobiledevice3.remote.common import TunnelProtocol
    from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
    from pymobiledevice3.remote.tunnel_service import get_remote_pairing_tunnel_services, start_tunnel
    from pymobiledevice3.services.diagnostics import DiagnosticsService

    services = []
    for _ in range(4):
        services = await get_remote_pairing_tunnel_services(udid=identifier)
        if services:
            break
    if not services:
        raise NotReachable(
            "Apple TV not found or it rejected the pairing. Check it is on, on the same network, "
            "and re-pair it if it was reset."
        )
    service, extras = services[0], services[1:]
    for extra in extras:
        await extra.close()

    async with start_tunnel(service, protocol=TunnelProtocol.TCP) as tunnel:
        async with RemoteServiceDiscoveryService((tunnel.address, tunnel.port)) as rsd:
            async with DiagnosticsService(rsd) as diagnostics:
                yield rsd, diagnostics


async def power(identifier: str, action: str) -> dict:
    # The device acts once the diagnostics connection closes, i.e. when the block exits.
    async with diagnostics_session(identifier) as (_rsd, diagnostics):
        await getattr(diagnostics, action)()
    return {"ok": True}


async def info(identifier: str) -> dict:
    async with diagnostics_session(identifier) as (rsd, diagnostics):
        props = rsd.peer_info.get("Properties", {})
        wifi = await diagnostics.get_wifi() or {}
    return {
        "ok": True,
        "info": {
            "build": props.get("BuildVersion"),
            "product_type": props.get("ProductType"),
            "serial": props.get("SerialNumber"),
            "wifi_band": wifi.get("IO80211Band"),
            "wifi_channel": wifi.get("IO80211Channel"),
            "wifi_bandwidth": wifi.get("IO80211ChannelBandwidth"),
        },
    }


async def main() -> dict:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("discover")
    p = sub.add_parser("pair")
    p.add_argument("identifier")
    p.add_argument("ip")
    p.add_argument("port", type=int)
    for name in ("restart", "info"):
        sub.add_parser(name).add_argument("identifier")
    args = parser.parse_args()

    if args.command == "discover":
        return await discover()
    if args.command == "pair":
        return await pair(args.identifier, args.ip, args.port)
    try:
        if args.command == "info":
            return await info(args.identifier)
        return await power(args.identifier, args.command)
    except NotReachable as err:
        return {"ok": False, "error": str(err), "reachable": False}


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    try:
        emit(**asyncio.run(main()))
    except Exception as err:  # noqa: BLE001 - report everything to the caller as JSON
        traceback.print_exc(file=sys.stderr)
        emit(ok=False, error=f"{type(err).__name__}: {err}")
        sys.exit(1)
