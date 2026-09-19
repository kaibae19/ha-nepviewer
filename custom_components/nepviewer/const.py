"""Constants for the NEPViewer integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "nepviewer"

MANUFACTURER: Final = "Northern Electric Power"

API_BASE: Final = "https://api.nepviewer.net/v2"

# The API answers every call with HTTP 200 and signals the real outcome in a
# JSON "code" field.
CODE_OK: Final = 200

# Codes seen from /sign-in for bad credentials: 202 is "user does not exist",
# 258 is "wrong password", which also reports a shrinking attempt counter --
# so a bad password must never be retried as if it were a transport error.
AUTH_FAIL_CODES: Final = {202, 203, 204, 258}

# The backend locks an account after a handful of failed sign-ins, so a forced
# re-login is not attempted more often than this.
MIN_RELOGIN_INTERVAL: Final = 300

REQUEST_TIMEOUT: Final = 20

CONF_TOKEN: Final = "token"
CONF_TOKEN_EXPIRES_AT: Final = "token_expires_at"

CONF_SCAN_INTERVAL_MINUTES: Final = "scan_interval_minutes"
CONF_STALE_AFTER_MINUTES: Final = "stale_after_minutes"

# The inverters upload every few minutes, so polling faster only burns requests.
DEFAULT_SCAN_INTERVAL_MINUTES: Final = 5
MIN_SCAN_INTERVAL_MINUTES: Final = 1
MAX_SCAN_INTERVAL_MINUTES: Final = 60

# The cloud keeps serving the last reading forever once an inverter stops
# uploading, so readings older than this are reported as unknown instead of
# being recorded as a flat line all night.
DEFAULT_STALE_AFTER_MINUTES: Final = 20
MIN_STALE_AFTER_MINUTES: Final = 5
MAX_STALE_AFTER_MINUTES: Final = 1440
