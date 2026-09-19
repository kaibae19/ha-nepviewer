# NEPViewer for Home Assistant

A Home Assistant integration for [NEP](https://northernep.com) (Northern Electric Power)
microinverters, polling the NEPViewer cloud with your normal account credentials.

Developed against a **BDM-1200-LV** (built-in WiFi, no gateway) on HA 2026.9.

## Features

- Config flow — email + password, no manual token wrangling
- Every inverter on the account is discovered automatically
- Per-PV-input (module) energy sensors, created only for inputs that report data
- Tokens are cached and reused across restarts, and refreshed before expiry
- Re-auth flow when credentials change
- Diagnostics download with account details redacted

### Entities per inverter

| Entity | Notes |
|---|---|
| Power | Current AC output, unknown while the data is stale (see below) |
| Energy today / yesterday / this month / this year / total | `Energy today` and `Energy total` are `total_increasing` and work in the Energy dashboard |
| Input *N* energy today / total | One pair per PV input that has produced anything |
| Input *N* power | Only created if NEP ever populates per-module live power (it currently reports 0) |
| Home power / Grid power | Only created when a smart meter is paired (`isConsumption`) |
| Last report, Status, Alert code, Alert, CO2 saved | Diagnostic |
| Reporting (connectivity), Problem | Binary sensors |

## Installation

### HACS (recommended)

HACS → three-dot menu → **Custom repositories** → add `https://github.com/kaibae19/ha-nepviewer`
as category **Integration**, then install **NEPViewer** and restart Home Assistant.

### Manual

Copy `custom_components/nepviewer/` into your HA `config/custom_components/` directory and restart.

Then: **Settings → Devices & Services → Add Integration → NEPViewer**.

## Options

| Option | Default | What it does |
|---|---|---|
| Polling interval | 5 min | The inverters upload every few minutes; polling faster mostly adds requests |
| Treat readings as stale after | 20 min | How old a reading may be before power sensors report unknown |

## API notes

The integration talks to `https://api.nepviewer.net/v2` — the same API the NEPViewer web UI
uses. It is undocumented and can change without warning. Three quirks are handled here, all
confirmed against a live account:

- **The cloud serves stale readings forever.** Once an inverter stops uploading, `totalNow`
  keeps returning its last value. Polling naively records a flat line all night, so power
  sensors go *unknown* once the last upload is older than the staleness threshold.
- **`lastUpdateTime` is the inverter's local wall clock stored as if it were UTC.** At a
  UTC-7 site every reading looks exactly 7 hours old. The integration reinterprets the
  timestamp in the site's timezone (from `device/detail`) and picks the most recent candidate
  that is not in the future, so it also behaves if NEP ever starts storing real UTC.
- **Per-module energy is in Wh but labelled kWh.** A module reporting `todayPower: 109`
  corresponds to a device total of `0.109 kWh`.

Sign-in failures return a shrinking attempt counter ("remaining attempts: 4"), so a wrong
password raises an auth error immediately rather than being retried, and forced re-logins
are rate limited.

`tools/probe_api.py` dumps raw API responses for your own account if you want to explore
further; it reads `NEPVIEWER_USER` / `NEPVIEWER_PASS` from the environment or `~/.env` and
never writes credentials to disk.

## Local alternative

This is a cloud integration: data is only as fresh and as available as NEPViewer.
NEP inverters post telemetry to `http://www.nepviewer.net/i.php` as an unencrypted 45-byte
binary payload, so a DNS override plus [nep-local-gw](https://github.com/Nic0w/nep-local-gw)
can capture it locally and publish to MQTT — documented for the BDM-400, and untested here.

## Tests

The value helpers are dependency-free and tested without a Home Assistant install:

```bash
python3 -m pytest tests -q
```

## Disclaimer

Not affiliated with, endorsed by, or supported by Northern Electric Power. NEPViewer is
their trademark. Use at your own risk.
