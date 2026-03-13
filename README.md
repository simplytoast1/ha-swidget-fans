# Swidget ERV — Custom Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io/)

A custom [Home Assistant](https://www.home-assistant.io/) integration for **Swidget ERV** (Energy Recovery Ventilator) controllers. Communicates entirely over the **local HTTP API** — no cloud required.

> **Note:** The existing [`haswidget2`](https://github.com/michaelkkehoe/haswidget2) integration does not support ERV devices (`pesna_fv05` host type). This integration was built specifically for them.

## Features

- **Fan control** — Turn the exhaust fan on/off, set speed by preset CFM values or percentage
- **Boost mode** — Toggle boost override via a switch entity
- **Light control** — Toggle the optional light output
- **Power monitoring** — Real-time and average wattage sensors
- **Exhaust CFM** — Dedicated sensor for airflow graphing
- **Condensation status** — Monitor the condensation management module
- **Balancing offset** — Adjust supply/exhaust balance via a number slider
- **Diagnostics** — Wi-Fi signal strength and self-diagnostic sensors
- **Auto-discovery** — Devices are detected via SSDP and DHCP

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** → **⋮** (top right) → **Custom repositories**
3. Add this repository URL: `https://github.com/simplytoast1/ha-swidget-fans` and select category **Integration**
4. Search for "Swidget ERV" and install
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/swidget_erv` folder into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Setup

### Automatic Discovery

If your Swidget ERV device is on the same network, it may be discovered automatically via SSDP or DHCP. You'll see a notification in Home Assistant prompting you to configure it.

### Manual Setup

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Swidget ERV"
3. Enter the device's IP address
4. Optionally enter the access key (if one was set during device provisioning)

## Entities

Once configured, the integration creates the following entities:

| Entity | Type | Description |
|--------|------|-------------|
| Exhaust Fan | `fan` | Main fan control — on/off, speed presets (CFM), percentage |
| Boost | `switch` | Toggle boost mode on/off |
| Light | `switch` | Toggle light output on/off |
| Power | `sensor` | Current power consumption (W) |
| Average Power | `sensor` | Average power consumption (W) |
| Exhaust CFM | `sensor` | Current exhaust airflow rate |
| Wi-Fi Signal | `sensor` | RSSI signal strength (dBm) |
| Condensation | `sensor` | Condensation module status |
| Self-Diagnostic | `sensor` | Device health (0 = healthy) |
| Balancing Offset | `number` | Supply/exhaust balance adjustment (-10 to +10) |

Entities are created dynamically based on what the device reports. If your device doesn't have a particular function (e.g. light), that entity won't be created.

## Fan Speed Control

The ERV only accepts specific CFM values. These are exposed as **preset modes** on the fan entity:

`50` · `60` · `70` · `80` · `90` · `100` · `110` · `120` · `130` · `150`

You can also use percentage-based speed control — percentages are mapped to the nearest allowed CFM step. Setting the fan to 0% (or turning it off) sets CFM to 0.

## Local API

This integration communicates with the device over its local HTTP API:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/summary` | GET | Device identity and capabilities |
| `/api/v1/state` | GET | Current device state (poll interval configurable in UI) |
| `/api/v1/command` | POST | Send control commands |

No cloud account or internet connection is needed. The device must be reachable on your local network.

## Troubleshooting

### Device not discovered
- Ensure the device is on the same network/VLAN as Home Assistant
- Try manual setup with the device's IP address
- Check that the device is powered on and connected to Wi-Fi

### Cannot connect during setup
- Verify the IP address is correct
- Check if the device has an access key set — enter it in the password field
- Ensure no firewall is blocking HTTP traffic to the device

### Entities show "Unavailable"
- The device may be offline or unreachable
- Check your network connectivity
- The integration will automatically recover when the device comes back online

## Contributing

Contributions are welcome! Some areas that could use exploration:

- **Timer function** — The device reports a "timer" function but the command format is unknown
- **Raw function** — Purpose unknown
- **Condensation states** — Only "dormant" has been observed so far
- **Balancing offset range** — The actual min/max values are not documented

## License

This project is licensed under the MIT License.
