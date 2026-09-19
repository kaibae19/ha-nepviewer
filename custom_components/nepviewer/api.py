"""Client for the NEPViewer cloud API.

The API answers every request with HTTP 200 and reports the real outcome in a
JSON ``code`` field, so status handling is done on the body, not the status
line. Auth is a bearer-style JWT passed bare in the ``Authorization`` header;
it is valid for 30 days and the backend counts failed sign-in attempts, so the
token is cached and reused rather than re-fetched on every poll.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from aiohttp import ClientError, ClientSession

from .const import (
    API_BASE,
    AUTH_FAIL_CODES,
    CODE_OK,
    MIN_RELOGIN_INTERVAL,
    REQUEST_TIMEOUT,
    TOKEN_INVALID_CODES,
)

_LOGGER = logging.getLogger(__name__)

# Refresh the token this long before it actually expires.
TOKEN_REFRESH_MARGIN = 24 * 60 * 60

BASE_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://user.nepviewer.com",
    "Oem": "NEP",
    "Client": "web",
    "App": "0",
}


class NepViewerError(Exception):
    """Base error for the NEPViewer API."""


class NepViewerAuthError(NepViewerError):
    """Credentials were rejected."""


class NepViewerConnectionError(NepViewerError):
    """The API could not be reached or returned an unusable answer."""


class NepViewerApi:
    """Minimal async client for api.nepviewer.net."""

    def __init__(
        self,
        session: ClientSession,
        account: str,
        password: str,
        token: str | None = None,
        token_expires_at: int | None = None,
        token_callback: Callable[[str, int], None] | None = None,
    ) -> None:
        """Initialise the client, optionally with a previously cached token."""
        self._session = session
        self._account = account
        self._password = password
        self._token = token
        self._token_expires_at = token_expires_at or 0
        self._token_callback = token_callback
        self._login_lock = asyncio.Lock()
        self._last_login_attempt = 0.0

    @property
    def token(self) -> str | None:
        """Return the current token, if any."""
        return self._token

    @property
    def token_expires_at(self) -> int:
        """Return the token expiry as a unix timestamp."""
        return self._token_expires_at

    def _token_usable(self) -> bool:
        """Return True if the cached token is present and not near expiry."""
        return bool(self._token) and (
            self._token_expires_at - TOKEN_REFRESH_MARGIN > time.time()
        )

    async def async_login(self) -> None:
        """Sign in and cache the resulting token."""
        async with self._login_lock:
            # Another coroutine may have refreshed it while we waited.
            if self._token_usable():
                return

            self._last_login_attempt = time.time()
            body = await self._async_raw_post(
                "/sign-in",
                {"account": self._account, "password": self._password},
                with_token=False,
            )

            code = body.get("code")
            if code in AUTH_FAIL_CODES:
                raise NepViewerAuthError(body.get("msg", "invalid credentials"))
            if code != CODE_OK:
                raise NepViewerConnectionError(
                    f"sign-in returned code {code}: {body.get('msg')}"
                )

            token_info = (body.get("data") or {}).get("tokenInfo") or {}
            token = token_info.get("token")
            if not token:
                raise NepViewerAuthError("sign-in returned no token")

            self._token = token
            self._token_expires_at = int(token_info.get("expiresAt") or 0)

            if self._token_callback is not None:
                self._token_callback(self._token, self._token_expires_at)

    async def _async_raw_post(
        self,
        path: str,
        payload: dict[str, Any],
        with_token: bool = True,
    ) -> dict[str, Any]:
        """POST to the API and return the decoded body."""
        headers = dict(BASE_HEADERS)
        if with_token and self._token:
            headers["Authorization"] = self._token

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self._session.post(
                    f"{API_BASE}{path}", json=payload, headers=headers
                )
                if response.status in (401, 403):
                    raise NepViewerAuthError(f"HTTP {response.status}")
                if response.status != 200:
                    raise NepViewerConnectionError(f"HTTP {response.status}")
                return await response.json(content_type=None)
        except TimeoutError as err:
            raise NepViewerConnectionError(f"timeout calling {path}") from err
        except ClientError as err:
            raise NepViewerConnectionError(f"error calling {path}: {err}") from err

    async def _async_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST an authenticated request, re-authenticating once if needed."""
        if not self._token_usable():
            await self.async_login()

        try:
            body: dict[str, Any] | None = await self._async_raw_post(path, payload)
        except NepViewerAuthError:
            # The token was rejected outright (HTTP 401/403). Credentials are
            # checked in async_login, so this is a dead token, not bad auth.
            body = None

        if body is not None and body.get("code") == CODE_OK:
            return body.get("data") or {}

        # The account holds exactly one valid token: signing in from the
        # NEPViewer app, the web UI or another Home Assistant instance kills
        # this one. That shows up either as HTTP 401 or as code 223, and the
        # cure is a fresh sign-in, so those bypass the re-login throttle.
        code = body.get("code") if body else None
        msg = body.get("msg") if body else "token rejected"
        invalidated = body is None or code in TOKEN_INVALID_CODES

        if not invalidated and (
            time.time() - self._last_login_attempt < MIN_RELOGIN_INTERVAL
        ):
            # Do not hammer sign-in for anything else: the backend locks
            # accounts out after a few failed attempts, and a wedged backend
            # would otherwise trigger a login on every poll.
            raise NepViewerConnectionError(f"{path} returned code {code}: {msg}")

        _LOGGER.debug(
            "%s rejected (code %s, %s); retrying after re-login", path, code, msg
        )
        self._token = None
        self._token_expires_at = 0
        await self.async_login()

        body = await self._async_raw_post(path, payload)
        if body.get("code") != CODE_OK:
            raise NepViewerConnectionError(
                f"{path} returned code {body.get('code')}: {body.get('msg')}"
            )

        return body.get("data") or {}

    async def async_get_devices(self) -> list[dict[str, Any]]:
        """Return every device registered on the account."""
        data = await self._async_post("/device/list", {"page": {"size": 100}})
        return list(data.get("list") or [])

    async def async_get_detail(self, sn: str) -> dict[str, Any]:
        """Return static metadata (model, firmware, timezone) for one device."""
        return await self._async_post("/device/detail", {"sn": sn})

    async def async_get_overview(self, sn: str) -> dict[str, Any]:
        """Return production statistics for one device."""
        return await self._async_post("/device/statistics/overview", {"sn": sn})
