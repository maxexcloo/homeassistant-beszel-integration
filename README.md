# Beszel Home Assistant Integration

[![Check](https://github.com/maxexcloo/homeassistant-beszel-integration/actions/workflows/check.yaml/badge.svg)](https://github.com/maxexcloo/homeassistant-beszel-integration/actions/workflows/check.yaml)
[![Version](https://img.shields.io/badge/version-0.2.1-blue.svg)](custom_components/beszel/manifest.json)
[![Licence](https://img.shields.io/badge/licence-AGPL--3.0-blue.svg)](LICENSE)

Monitor Beszel systems in Home Assistant with automatically discovered
sensors for hardware, operating system, storage, and network statistics.

Requires Home Assistant 2026.9.4 or newer.

## Quick Start

1. Add `https://github.com/maxexcloo/homeassistant-beszel-integration` as an
   Integration custom repository in HACS.
2. Install **Beszel** and restart Home Assistant.
3. Open **Settings → Devices & Services → Add Integration**.
4. Search for **Beszel** and enter the Hub URL, username, and password.

## Features

- Battery level and charging state.
- Cached hardware and operating system details survive temporary details API failures.
- Cached system metrics survive temporary per-system API failures.
- CPU model, topology, and utilisation.
- Disk capacity, throughput, latency, and I/O utilisation.
- Dynamic discovery when systems or metrics appear after setup.
- GPU memory, package power, power draw, and utilisation.
- Memory, swap, network, operating system, status, and uptime sensors.
- Multiple Beszel Hubs and systems without device or entity collisions.
- Per-filesystem and temperature sensors.
- Reauthentication and reconfiguration through Home Assistant.
- Temporary connection failures and rate limits retry without prompting for credentials.
- Translated entity names and enum states.

## Installation

### HACS

1. Open **HACS → Integrations → Custom repositories**.
2. Add `https://github.com/maxexcloo/homeassistant-beszel-integration`.
3. Select the **Integration** category.
4. Install **Beszel** and restart Home Assistant.

### Manual

From a checkout of this repository, copy the integration into your Home Assistant
configuration directory:

```bash
mkdir -p /config/custom_components/beszel
cp -R custom_components/beszel/. /config/custom_components/beszel/
```

Restart Home Assistant after copying the files.

## Usage

### Configuration

Enter the following values when adding the integration:

- **Host**: The Beszel Hub URL, such as `http://192.168.1.100:8090`.
- **Username**: The Hub username or email address.
- **Password**: The Hub password.

Home Assistant creates sensors only when Beszel reports the corresponding data.
New systems and metrics are discovered during later updates without reloading the
integration. Missing measurements remain unavailable rather than being reported as
zero. If one system temporarily fails while the Hub remains reachable, its cached
metrics are retained until a later successful update.

To expose additional disks, configure the Beszel agent using the
[additional disks guide](https://beszel.dev/guide/additional-disks). Each reported
filesystem receives its own capacity, throughput, and I/O sensors.

Use **Settings → Devices & services → Beszel → ⋮ → Reconfigure** to change the Hub or
credentials. Home Assistant also prompts for a new password when authentication
expires.

## Contributing

1. Fork the repository and create a feature branch.
2. Run `mise run setup` to install the pinned development tools.
3. Follow the repository standards in `AGENTS.md`.
4. Run the same checks as CI:

   ```bash
   mise run check
   ```

5. Submit a pull request with tests and documentation for behavioural changes.

Unit tests use lightweight Home Assistant and PocketBase test doubles. GitHub CI
also runs HACS and Hassfest validation; the unit tests do not exercise a running
Home Assistant instance or Beszel Hub.

## Licence

Licensed under the [GNU Affero General Public License v3.0](LICENSE).
