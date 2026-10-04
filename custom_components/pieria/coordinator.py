"""Data coordinator for Pieria."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, replace
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    Display,
    Info,
    PieriaApiError,
    PieriaAuthError,
    PieriaClient,
    PieriaConnectionError,
    Playlist,
    Quiet,
)
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FEATURE_QUIET,
    MIN_SCAN_INTERVAL,
    OPTIMISTIC_TTL,
    PLAYLIST_REFRESH_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class PieriaData:
    """One coordinator snapshot."""

    displays: dict[str, Display] = field(default_factory=dict)
    quiet: Quiet | None = None
    playlists: list[Playlist] = field(default_factory=list)


@dataclass
class _Pending:
    """An optimistic patch held until the display's updated_at advances."""

    baseline: str | None
    expires: float
    patch: dict[str, Any]


@dataclass
class PieriaRuntimeData:
    """Stored on the config entry."""

    client: PieriaClient
    coordinator: PieriaCoordinator
    info: Info


type PieriaConfigEntry = ConfigEntry[PieriaRuntimeData]


class PieriaCoordinator(DataUpdateCoordinator[PieriaData]):
    """Polls /displays and /quiet; playlists less often."""

    config_entry: PieriaConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: PieriaConfigEntry,
        client: PieriaClient,
        features: frozenset[str] = frozenset(),
    ) -> None:
        interval = max(
            MIN_SCAN_INTERVAL, int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self.features = features
        self._pending: dict[str, _Pending] = {}
        self._playlists: list[Playlist] = []
        self._playlists_at: float | None = None

    async def _async_update_data(self) -> PieriaData:
        try:
            displays = await self.client.displays()
            quiet: Quiet | None = None
            if FEATURE_QUIET in self.features:
                try:
                    quiet = await self.client.get_quiet()
                except PieriaAuthError:
                    raise
                except PieriaApiError as err:
                    _LOGGER.debug("quiet state unavailable: %s", err)
            now = time.monotonic()
            if self._playlists_at is None or now - self._playlists_at >= PLAYLIST_REFRESH_SECONDS:
                try:
                    self._playlists = await self.client.playlists()
                    self._playlists_at = now
                except PieriaApiError as err:
                    if isinstance(err, PieriaAuthError):
                        raise
                    _LOGGER.debug("playlists refresh failed: %s", err)
        except PieriaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (PieriaConnectionError, PieriaApiError) as err:
            raise UpdateFailed(str(err)) from err
        by_id = {d["id"]: d for d in displays}
        self._apply_pending(by_id)
        return PieriaData(displays=by_id, quiet=quiet, playlists=self._playlists)

    def _apply_pending(self, displays: dict[str, Display]) -> None:
        """Overlay optimistic patches until updated_at advances or the TTL runs out."""
        now = time.monotonic()
        for display_id, pending in list(self._pending.items()):
            display = displays.get(display_id)
            if (
                display is None
                or display.get("updated_at") != pending.baseline
                or now >= pending.expires
            ):
                del self._pending[display_id]
                continue
            display.update(pending.patch)  # type: ignore[typeddict-item]

    async def async_after_command(self, display_id: str, patch: dict[str, Any] | None) -> None:
        """Show the expected state now, then refresh to learn the real one."""
        display = self.data.displays.get(display_id) if self.data else None
        if patch and display is not None:
            existing = self._pending.get(display_id)
            self._pending[display_id] = _Pending(
                baseline=existing.baseline if existing else display.get("updated_at"),
                expires=time.monotonic() + OPTIMISTIC_TTL,
                patch={**(existing.patch if existing else {}), **patch},
            )
            displays = {**self.data.displays, display_id: {**display, **patch}}
            self.async_set_updated_data(replace(self.data, displays=displays))  # type: ignore[arg-type]
        await self.async_request_refresh()

    def set_quiet_state(self, quiet: Quiet) -> None:
        """Adopt the state POST /quiet returned."""
        self.async_set_updated_data(replace(self.data, quiet=quiet))
