# Beszel Home Assistant Integration

[![Check](https://github.com/maxexcloo/homeassistant-beszel-integration/actions/workflows/check.yaml/badge.svg)](https://github.com/maxexcloo/homeassistant-beszel-integration/actions/workflows/check.yaml)
[![Licence](https://img.shields.io/badge/licence-AGPL--3.0-blue.svg)](LICENSE)

Monitor Beszel systems, containers and network probes in Home Assistant.

Requires Home Assistant 2026.11.1 or newer and Beszel 0.18.0 or newer.

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

## Configuration

Open **Settings → Devices & Services → Add Integration**, search for **Beszel**,
and enter:

- **Host**: The Beszel Hub URL, such as `http://192.168.1.100:8090`.
- **Username**: The Hub username or email address.
- **Password**: The Hub password.

To monitor more disks, configure the Beszel agent using the
[additional disks guide](https://beszel.dev/guide/additional-disks). Network
probe sensors need Beszel Hub and agents 0.20.0 or newer with
[Network Monitors](https://beszel.dev/guide/network-monitors) configured.

## Contributing

Install the
[shared Mise configuration](https://github.com/maxexcloo/dotfiles#shared-tools--tasks)
before running local Mise tasks.

Follow [AGENTS.md](AGENTS.md) and submit a pull request. Before submitting, run:

```bash
mise run check
```

## Licence

Licensed under the [GNU Affero General Public License v3.0](LICENSE).
