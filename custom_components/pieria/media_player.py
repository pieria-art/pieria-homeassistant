"""Pieria media_player: the hero entity per display."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import Display
from .const import DOMAIN, FEATURE_PAUSE, FEATURE_SHOW, NON_NAVIGABLE_KINDS
from .coordinator import PieriaConfigEntry
from .entity import PieriaDisplayEntity, call_api, setup_display_entities

PARALLEL_UPDATES = 1

SERVICE_SHOW_ARTWORK = "show_artwork"
ATTR_ARTWORK_ID = "artwork_id"
ATTR_QUERY = "query"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PieriaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up media players."""
    if FEATURE_SHOW in entry.runtime_data.coordinator.features:
        platform = entity_platform.async_get_current_platform()
        platform.async_register_entity_service(
            SERVICE_SHOW_ARTWORK,
            {
                vol.Optional(ATTR_ARTWORK_ID): cv.positive_int,
                vol.Optional(ATTR_QUERY): cv.string,
            },
            "async_show_artwork",
        )
    setup_display_entities(entry, async_add_entities, lambda e, d: [PieriaMediaPlayer(e, d["id"])])


class PieriaMediaPlayer(PieriaDisplayEntity, MediaPlayerEntity):
    """A Pieria display as a media player."""

    _attr_name = None
    _attr_media_content_type = MediaType.IMAGE
    _attr_media_image_remotely_accessible = False

    def __init__(self, entry: PieriaConfigEntry, display_id: str) -> None:
        super().__init__(entry, display_id, "media_player")

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """By kind (e-ink / frame cannot skip) and server features (pause)."""
        features = MediaPlayerEntityFeature.SELECT_SOURCE
        display = self.display
        if (display or {}).get("kind") not in NON_NAVIGABLE_KINDS:
            features |= (
                MediaPlayerEntityFeature.NEXT_TRACK | MediaPlayerEntityFeature.PREVIOUS_TRACK
            )
        if FEATURE_PAUSE in self.coordinator.features:
            features |= MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.PAUSE
        return features

    @property
    def _artwork(self) -> dict[str, Any] | None:
        display: Display | None = self.display
        return display.get("artwork") if display else None

    @property
    def state(self) -> MediaPlayerState | None:
        """Playing / paused / off (not live)."""
        display = self.display
        if display is None:
            return None
        if not display["live"]:
            return MediaPlayerState.OFF
        if display.get("paused"):
            return MediaPlayerState.PAUSED
        return MediaPlayerState.PLAYING

    @property
    def media_title(self) -> str | None:
        """Artwork title."""
        art = self._artwork
        return art.get("title") if art else None

    @property
    def media_artist(self) -> str | None:
        """Artwork artist."""
        art = self._artwork
        return art.get("artist") if art else None

    @property
    def media_content_id(self) -> str | None:
        """Artwork id."""
        art = self._artwork
        return str(art["id"]) if art else None

    @property
    def media_image_url(self) -> str | None:
        """Absolute URL of the current artwork (built from the configured host)."""
        art = self._artwork
        if not art or not art.get("image_url"):
            return None
        return self._api.absolute_url(art["image_url"])

    @property
    def source_list(self) -> list[str]:
        """Playlist names."""
        return [p["name"] for p in self.coordinator.data.playlists]

    @property
    def source(self) -> str | None:
        """Current playlist name."""
        display = self.display
        return display.get("playlist") if display else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Extra artwork and display facts."""
        display = self.display
        if display is None:
            return {}
        art = display.get("artwork") or {}
        return {
            "kind": display["kind"],
            "render_mode": display.get("mode"),
            "last_seen": display["last_seen"],
            "updated_at": display.get("updated_at"),
            "artwork_year": art.get("year"),
            "artwork_is_personal": art.get("is_personal"),
        }

    async def async_media_play(self) -> None:
        """Resume."""
        await self.async_command("resume", {"paused": False})

    async def async_media_pause(self) -> None:
        """Pause."""
        await self.async_command("pause", {"paused": True})

    async def async_media_next_track(self) -> None:
        """Next artwork."""
        await self.async_command("next")

    async def async_media_previous_track(self) -> None:
        """Previous artwork."""
        await self.async_command("previous")

    async def async_select_source(self, source: str) -> None:
        """Switch playlist, by id when /playlists knows the name, else by name."""
        match = next((p for p in self.coordinator.data.playlists if p["name"] == source), None)
        if match is not None:
            patch = {"playlist": source, "playlist_id": match["id"]}
            await self.async_command("set_playlist", patch, playlist_id=match["id"])
        else:
            await self.async_command("set_playlist", {"playlist": source}, playlist=source)

    async def async_show_artwork(
        self, artwork_id: int | None = None, query: str | None = None
    ) -> None:
        """Show a specific artwork now, by id or first search hit."""
        if (artwork_id is None) == (query is None):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="artwork_id_or_query"
            )
        if artwork_id is None:
            results = await call_api(self.display_id, self._api.search(query or "", 1))
            items = results.get("items") or []
            if not items:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="no_search_results",
                    translation_placeholders={"query": query or ""},
                )
            artwork_id = items[0]["id"]
        await call_api(self.display_id, self._api.show(self.display_id, artwork_id))
        await self.coordinator.async_after_command(self.display_id, None)
