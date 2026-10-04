"""Current-artwork image entity."""

from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import PieriaConfigEntry
from .entity import PieriaDisplayEntity, setup_display_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PieriaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up image entities."""
    setup_display_entities(
        entry, async_add_entities, lambda e, d: [PieriaArtworkImage(hass, e, d["id"])]
    )


class PieriaArtworkImage(PieriaDisplayEntity, ImageEntity):
    """The artwork currently on the display."""

    _attr_translation_key = "artwork"
    _attr_content_type = "image/jpeg"

    def __init__(self, hass: HomeAssistant, entry: PieriaConfigEntry, display_id: str) -> None:
        PieriaDisplayEntity.__init__(self, entry, display_id, "artwork")
        ImageEntity.__init__(self, hass)
        self._artwork_id: int | None = None
        self._refresh_url()
        self._attr_image_last_updated = dt_util.utcnow()

    def _refresh_url(self) -> None:
        display = self.display
        art = display.get("artwork") if display else None
        self._attr_image_url = (
            self._api.absolute_url(art["image_url"]) if art and art.get("image_url") else None
        )
        self._artwork_id = art["id"] if art else None

    @callback
    def _handle_coordinator_update(self) -> None:
        previous = self._artwork_id
        self._refresh_url()
        if self._artwork_id != previous:
            self._cached_image = None
            self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()
