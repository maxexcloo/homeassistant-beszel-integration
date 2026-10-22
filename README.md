# Beszel Home Assistant Integration

[![Check](https://github.com/maxexcloo/homeassistant-beszel-integration/actions/workflows/check.yaml/badge.svg)](https://github.com/maxexcloo/homeassistant-beszel-integration/actions/workflows/check.yaml)
[![Licence](https://img.shields.io/badge/licence-AGPL--3.0-blue.svg)](LICENSE)

Monitor Beszel systems in Home Assistant. Sensors for hardware, operating
system, storage and network statistics are discovered automatically.

Requires Home Assistant 2026.10.2 or newer and Beszel 0.18.0 or newer.

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
- Per-filesystem and temperature sensors with distinct identifiers for each metric.
- Reauthentication and reconfiguration through Home Assistant.
- Removal of devices for systems the Hub no longer reports.
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

Open **Settings → Devices & Services → Add Integration**, search for **Beszel**,
and enter:

- **Host**: The Beszel Hub URL, such as `http://192.168.1.100:8090`.
- **Username**: The Hub username or email address.
- **Password**: The Hub password.

Home Assistant only creates a sensor when Beszel reports data for it. Existing
temperature entities are migrated automatically and keep their entity IDs and
customisations. New systems and metrics are picked up during later updates
without reloading the integration. Missing measurements show as unavailable, not
zero. If one system briefly fails while the Hub is still reachable, its cached
metrics stay cached. Measurement sensors are available only while the system is
up and the latest one-minute statistics record is no more than five minutes old.
Missing or invalid record timestamps make measurements unavailable; static
information and the system status remain available.

Capacity and throughput readings use decimal GB, MB and MB/s. Beszel's binary
source quantities are converted to match those existing units. Entity and
statistics IDs are unchanged; previously recorded values are not rewritten, so
historical graphs retain the earlier unit error before this correction.

To add more disks, configure the Beszel agent using the
[additional disks guide](https://beszel.dev/guide/additional-disks). Each reported
filesystem gets its own capacity, throughput and I/O sensors.
Filesystem throughput uses current byte-rate fields when available and supports
older Hub measurements without changing existing entity IDs.

Use **Settings → Devices & Services → Beszel → ⋮ → Reconfigure** to change the Hub or
credentials. Home Assistant also prompts for a new password when authentication
expires.

## Contributing

Install the [shared Mise configuration](https://github.com/maxexcloo/dotfiles#shared-tools--tasks)
before running local Mise tasks.

1. Fork the repository and create a feature branch.
2. Follow the repository standards in `AGENTS.md`.
3. Run the same checks as CI:

   ```bash
   mise run check
   ```

4. Submit a pull request with tests and documentation for behavioural changes.

GitHub CI also runs HACS and Hassfest validation.

## Licence

Licensed under the [GNU Affero General Public License v3.0](LICENSE).
