"""Data coordinator for Pieria."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import timedelta

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
    MIN_SCAN_INTERVAL,
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
class PieriaRuntimeData:
    """Stored on the config entry."""

    client: PieriaClient
    coordinator: PieriaCoordinator
    info: Info


type PieriaConfigEntry = ConfigEntry[PieriaRuntimeData]


class PieriaCoordinator(DataUpdateCoordinator[PieriaData]):
    """Polls /displays and /quiet; playlists less often."""

    config_entry: PieriaConfigEntry

    def __init__(self, hass: HomeAssistant, entry: PieriaConfigEntry, client: PieriaClient) -> None:
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
        self._playlists: list[Playlist] = []
        self._playlists_at: float | None = None

    async def _async_update_data(self) -> PieriaData:
        try:
            displays = await self.client.displays()
            quiet: Quiet | None
            try:
                quiet = await self.client.get_quiet()
            except PieriaAuthError:
                raise
            except PieriaApiError as err:
                _LOGGER.debug("quiet state unavailable: %s", err)
                quiet = None
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
        return PieriaData(
            displays={d["id"]: d for d in displays},
            quiet=quiet,
            playlists=self._playlists,
        )
