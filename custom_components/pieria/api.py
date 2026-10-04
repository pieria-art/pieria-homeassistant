"""Async client for the Pieria public API v1. No Home Assistant imports."""

from __future__ import annotations

import asyncio
from typing import Any, NotRequired, TypedDict

import aiohttp

API_PREFIX = "/api/v1"
REQUEST_TIMEOUT = 10


class PieriaError(Exception):
    """Base error."""


class PieriaConnectionError(PieriaError):
    """The server could not be reached."""


class PieriaApiError(PieriaError):
    """The server answered with an error envelope."""

    def __init__(self, code: str, message: str = "", status: int | None = None) -> None:
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code
        self.message = message
        self.status = status


class PieriaAuthError(PieriaApiError):
    """401 / 403 - bad token or missing scope."""


class Artwork(TypedDict):
    """ArtworkCompact."""

    id: int
    title: str | None
    artist: str | None
    year: str | None
    image_url: str
    thumb_url: str
    is_personal: bool


class Display(TypedDict):
    """Display."""

    id: str
    name: NotRequired[str]
    live: bool
    last_seen: str
    kind: str
    playlist: str | None
    playlist_id: NotRequired[int | None]
    updated_at: NotRequired[str]
    paused: NotRequired[bool]
    mode: str | None
    artwork: Artwork | None


class Info(TypedDict):
    """Server identity."""

    name: str
    version: str
    api_version: int
    appliance_mode: bool
    server_id: str
    display_name: str | None
    api_features: NotRequired[list[str]]
    token_scopes: NotRequired[list[str]]


class Playlist(TypedDict):
    """PlaylistSummary."""

    id: int
    name: str
    artwork_count: int
    display_time: int
    shuffle: bool
    default_mode: str
    is_personal: bool


class Quiet(TypedDict):
    """Manual/scheduled quiet state."""

    active: bool
    mode: str
    source: str
    until: str | None


class PieriaClient:
    """Thin typed wrapper over the v1 REST API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
        token: str,
    ) -> None:
        self._session = session
        self.host = host
        self.port = port
        self._token = token

    @property
    def base_url(self) -> str:
        """Server root (no API prefix)."""
        host = f"[{self.host}]" if ":" in self.host and not self.host.startswith("[") else self.host
        return f"http://{host}:{self.port}"

    def absolute_url(self, path: str) -> str:
        """Resolve a server-absolute media path."""
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.base_url}{path}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{API_PREFIX}{path}"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                resp = await self._session.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                async with resp:
                    if resp.status < 400:
                        return await resp.json(content_type=None)
                    try:
                        body = await resp.json(content_type=None)
                    except (aiohttp.ClientError, ValueError):
                        body = None
        except (TimeoutError, aiohttp.ClientError) as err:
            raise PieriaConnectionError(str(err) or type(err).__name__) from err
        code, message = f"http_{resp.status}", ""
        if isinstance(body, dict):
            err_body = body.get("error")
            if isinstance(err_body, dict):
                code = str(err_body.get("code", code))
                message = str(err_body.get("message", ""))
            elif "detail" in body:
                code = "validation_error"
        if resp.status in (401, 403):
            raise PieriaAuthError(code, message, resp.status)
        raise PieriaApiError(code, message, resp.status)

    async def info(self) -> Info:
        """GET /info."""
        return await self._request("GET", "/info")

    async def displays(self) -> list[Display]:
        """GET /displays."""
        return await self._request("GET", "/displays")

    async def playlists(self) -> list[Playlist]:
        """GET /playlists."""
        return await self._request("GET", "/playlists")

    async def playlist_artworks(
        self, playlist_id: int, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        """GET /playlists/{id}/artworks."""
        return await self._request(
            "GET",
            f"/playlists/{playlist_id}/artworks",
            params={"limit": limit, "offset": offset},
        )

    async def artwork(self, artwork_id: int) -> dict[str, Any]:
        """GET /artworks/{id}."""
        return await self._request("GET", f"/artworks/{artwork_id}")

    async def search(self, query: str, limit: int = 20) -> dict[str, Any]:
        """GET /search."""
        return await self._request("GET", "/search", params={"q": query, "limit": limit})

    async def command(
        self,
        display_id: str,
        action: str,
        *,
        playlist: str | None = None,
        playlist_id: int | None = None,
        mode: str | None = None,
    ) -> None:
        """POST /displays/{id}/commands."""
        body: dict[str, Any] = {"action": action}
        if playlist is not None:
            body["playlist"] = playlist
        if playlist_id is not None:
            body["playlist_id"] = playlist_id
        if mode is not None:
            body["mode"] = mode
        await self._request("POST", f"/displays/{display_id}/commands", json=body)

    async def show(self, display_id: str, artwork_id: int) -> None:
        """POST /displays/{id}/show."""
        await self._request("POST", f"/displays/{display_id}/show", json={"artwork_id": artwork_id})

    async def get_quiet(self) -> Quiet:
        """GET /quiet."""
        return await self._request("GET", "/quiet")

    async def set_quiet(self, mode: str, until: str | None = None) -> Quiet:
        """POST /quiet with mode on | off | auto (until is ignored for auto)."""
        body: dict[str, Any] = {"mode": mode}
        if until is not None and mode != "auto":
            body["until"] = until
        return await self._request("POST", "/quiet", json=body)

    async def get_schedule(self) -> dict[str, Any]:
        """GET /schedule."""
        return await self._request("GET", "/schedule")

    async def patch_schedule(self, **fields: Any) -> dict[str, Any]:
        """PATCH /schedule."""
        return await self._request("PATCH", "/schedule", json=fields)
