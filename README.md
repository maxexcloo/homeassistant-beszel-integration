# Beszel Home Assistant Integration

[![Check](https://github.com/maxexcloo/homeassistant-beszel-integration/actions/workflows/check.yaml/badge.svg)](https://github.com/maxexcloo/homeassistant-beszel-integration/actions/workflows/check.yaml)
[![Licence](https://img.shields.io/badge/licence-AGPL--3.0-blue.svg)](LICENSE)

Monitor Beszel systems in Home Assistant. Sensors for hardware, operating
system, storage and network statistics are discovered automatically.

Requires Home Assistant 2026.10.4 or newer and Beszel 0.18.0 or newer.

## Features

- Battery level and charging state.
- Configurable update interval.
- Host statistics record timestamps and container last-report timestamps.
- Container instance health, CPU, memory and total network rate.
- CPU model, topology, and utilisation.
- Diagnostics download with credentials redacted.
- Disk capacity, throughput, latency, and I/O utilisation.
- Dynamic discovery when systems or metrics appear after setup.
- GPU memory, package power, power draw, and utilisation.
- Memory, swap, network, operating system, status, and uptime sensors.
- Multiple Beszel Hubs and systems without device or entity collisions.
- Network probe response times and packet loss in a separate Network Probes device per Hub.
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

Home Assistant only creates a sensor when Beszel reports data for it. New systems
and metrics are picked up during later updates without reloading the integration.
Missing measurements show as unavailable, not zero. If the Hub briefly fails to
return a system's metrics or details, the cached values are kept. Measurement
sensors are available only while the system is up and the latest one-minute
statistics record is no more than five minutes old. Missing or invalid record
timestamps make measurements unavailable; static information and the system
status remain available.

Capacity and throughput readings use decimal GB, MB and MB/s; Beszel's binary
quantities are converted.

To add more disks, configure the Beszel agent using the
[additional disks guide](https://beszel.dev/guide/additional-disks). Each reported
filesystem gets its own capacity, throughput and I/O sensors. Read and write
latency, busy time and weighted I/O sensors are disabled by default; enable them on
the device page when you need them.

Statistics are fetched every minute by default. To store fewer states in the
recorder, open **Settings → Devices & Services → Beszel → Configure** and set a
longer **Update Interval**, up to 60 minutes.

Use **Settings → Devices & Services → Beszel → ⋮ → Reconfigure** to change the Hub or
credentials. Home Assistant also prompts for a new password when authentication
expires.

### Network Probes

With Beszel Hub and agents 0.20.0 or newer, configure
[Network Monitors](https://beszel.dev/guide/network-monitors) in Beszel. When any
system reports probe measurements, the integration automatically creates a
separate **Network Probes** device in that Hub's integration entry. Older Hubs
continue to work without probe sensors.

Each monitor provides average, minimum and maximum response time in milliseconds
and packet loss in percent from its latest one-minute statistics record. Sensor
names include the probing system, target, protocol and TCP port where applicable.
Monitors of the same target from different systems or Hubs remain distinct.

Missing measurements and response times without successful probes remain unknown.
Disabled probes and probes on offline or removed systems are unavailable. Cached
samples survive temporary API failures, but become unavailable after five minutes
or the configured probe interval plus two minutes, whichever is longer. New probes
and measurements are discovered during later updates without reloading.

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

## Container reports and freshness

Each reported container instance has a child device under its Beszel host, with
health, CPU usage, memory used, total network rate and a diagnostic Last Hub report
timestamp. New instances appear on later polls without reloading the integration.
Memory is converted from Beszel's MiB to decimal MB. Total network rate is bytes
per second, already calculated by Beszel; it is not a cumulative counter.

The Last statistics record diagnostic on each host is the creation time of its
latest one-minute Hub statistics record. Last Hub report is the numeric receipt
time stored by the Hub for that container. Neither is the agent's exact measurement
time, and successful HA polling never refreshes those timestamps.

The existing host measurement guard remains unchanged: host up, valid aware record
time, and age from zero through five minutes inclusive. Container health and
metrics independently require host up and a valid container receipt time within
five minutes. Valid old diagnostic timestamps remain visible, including when the
host is down. Missing, malformed and future timestamps are unknown. A failed Hub
update or an absent host/container makes the corresponding entities unavailable.
Partial container query failures retain cached values and their original times;
a successful empty inventory clears them. Missing values are never converted to
zero. A container-only query failure does not prevent host/probe updates.

Health distinguishes starting, healthy, unhealthy, no health data and unknown.
Beszel health code zero means no usable health data; it does not mean healthy.
Normal Beszel discovery covers running containers and can omit containers whose
statistics failed. Absence therefore never means stopped, and this integration
does not expose a running/stopped binary sensor.

Identity includes the HA entry, Beszel host and runtime container ID. Renaming an
instance updates its name/image metadata without changing entity IDs. Recreating
a container creates new entities even when its name is unchanged. This is not a
stable service identity or an expected-service inventory. Removed instances retain
registry history; manual device removal is allowed after confirmed non-reporting,
not during partial failures. A collection 404 disables container discovery without
failing host updates; 401/403 still request reauthentication.

The integration only lists container records visible to its existing Hub account.
It does not query Docker directly or read container logs/inspect data. No account
privilege increase is required. Lifecycle counters, OOM/exit evidence, required
mount checks, stable logical workload identity and exact agent observation times
remain outside this feature. These entities also do not implement MQTT expiry or
ACLs, independent service probes, or suspected-stall diagnostics.

## Licence

Licensed under the [GNU Affero General Public License v3.0](LICENSE).
