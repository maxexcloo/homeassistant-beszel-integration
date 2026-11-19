# Beszel Home Assistant Integration

Monitor Beszel systems, containers and network probes in Home Assistant.

Requires Home Assistant 2026.11.2 or newer and Beszel 0.18.0 or newer.

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

## Development

Install the
[shared Mise configuration](https://github.com/maxexcloo/dotfiles#shared-tools--tasks),
then run the checks from the repository root:

```bash
mise run check
```

## Licence

AGPL-3.0 - see [LICENSE](LICENSE).
