<p align="center">
  <img src="custom_components/apple_tv_reboot/brand/icon@2x.png" alt="Apple TV Reboot" width="160">
</p>

# Apple TV Reboot for Home Assistant

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=usersaynoso&repository=Apple-TV-Reboot-for-Home-Assistant&category=integration)
[![Validate](https://github.com/usersaynoso/Apple-TV-Reboot-for-Home-Assistant/actions/workflows/validate.yaml/badge.svg)](https://github.com/usersaynoso/Apple-TV-Reboot-for-Home-Assistant/actions/workflows/validate.yaml)

Restart an Apple TV from Home Assistant with a real tvOS restart, with no remote button presses and no
Settings > System > Restart menu walk. It also adds a few things the built-in Apple TV integration does not offer.

This project is not affiliated with or endorsed by Apple. Apple TV and tvOS are trademarks of Apple Inc.

## What you get per Apple TV

- **Restart** button.
- **Reachable** binary sensor: the Apple TV itself answered (checked every 5 minutes and after a restart). More direct than
  the media player state, which can read off or idle on a healthy TV.
- Diagnostic sensors: tvOS build, Wi-Fi band, channel and channel width. Model, serial and build also appear on the device page.
- Service `apple_tv_reboot.restart_and_wait`: target the Restart button. It restarts, waits for the Apple TV to go down and
  come back, then returns, or fails after `timeout` (default 300 s). Use it in scripts instead of guessing with delays.

### Not included, on purpose

- **Power off:** the built-in Apple TV integration's `media_player.turn_off` already does the same as holding the power button.
- **Sleep:** the diagnostics `Sleep` request only blanks the screen for a few seconds on tvOS 27; it does not enter standby.
- **Shutdown:** tvOS cannot be woken over the network, so a real shutdown could leave the Apple TV off until someone presses a button.
- **HDMI state and uptime:** the readings were not reliable (HDMI reported "unplugged" on a connected TV).

## Install

1. In HACS, add this repository as a custom repository (type: Integration), or use the button above. Install it and restart Home Assistant.
2. Go to Settings > Devices & services > Add integration > **Apple TV Reboot**.
3. Wait for the runtime install (about a minute). Then, on the Apple TV, open
   **Settings > Remotes and Devices > Remote App and Devices** and leave that screen showing. Press Submit.
4. Pick the Apple TV and type the PIN it shows.

Use the button in automations with `button.press` on `button.<name>_restart`, or call `apple_tv_reboot.restart_and_wait`.

```yaml
action: apple_tv_reboot.restart_and_wait
target:
  entity_id: button.living_room_tv_restart
data:
  timeout: 300
```

## Requirements

- tvOS 17 or later. The Apple TV only offers pairing while the Remote App and Devices screen is open.
- Home Assistant 2024.6 or later.
- Home Assistant must be able to create a network tunnel interface: it needs root, `/dev/net/tun` and host networking.
  The Home Assistant Container install run with `--privileged --network host` meets this. Other install types are untested.
- Home Assistant and the Apple TV on the same network, with mDNS working between them.
- Internet access on first setup, to download the pinned Python packages.

## How it works

tvOS 17 and later supports the "remote pairing" that Xcode uses for wireless debugging. The integration pairs once with the
PIN shown on the Apple TV. On each restart it opens a tunnel to the Apple TV and sends the device's diagnostics `Restart`
request, using [pymobiledevice3](https://github.com/doronz88/pymobiledevice3). The Apple TV is down for about 30 to 40 seconds.

pymobiledevice3 cannot be a normal Home Assistant requirement: its dependencies clash with Home Assistant's, and one of them
(`pylzss`) needs a compiler on Alpine. So on first setup the integration builds its own virtualenv in
`<config>/atv_reboot/venv` from the pinned `requirements-runtime.txt`, and runs `atv_helper.py` with that venv's Python. That
list leaves out `pylzss`, which is only used for firmware images. Pairing records are kept under `<config>/atv_reboot/home`, so
they survive container recreation and are included in Home Assistant backups. Treat that folder as sensitive: the records
let a host that holds them control the paired Apple TV.

Everything is local. Nothing is sent to a cloud service, other than the one-time package download.

## Tested on

One Apple TV 4K (AppleTV14,1) on tvOS 27, with Home Assistant Container on Alpine Linux and Python 3.14. Other models,
tvOS versions and Home Assistant install types may behave differently. Reports are welcome in the issue tracker.

## Notes and limits

- Only one tunnel to an Apple TV can be open at a time. A restart fails if something else, such as `pymobiledevice3` on another
  machine, already holds one. Inside Home Assistant all calls share a lock.
- The Apple TV's pairing id is not stable. If the Apple TV is factory reset, delete the entry and run the setup flow again.
- The restart is a clean reboot requested through the device's diagnostics service, not a power cut.

## Licence

MIT. See [LICENSE](LICENSE).
