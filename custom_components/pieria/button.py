"""Show-placard button (canvas displays only)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import KIND_CANVAS
from .coordinator import PieriaConfigEntry
from .entity import PieriaDisplayEntity, setup_display_entities

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PieriaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons."""
    setup_display_entities(
        entry,
        async_add_entities,
        lambda e, d: [PieriaPlacardButton(e, d["id"])] if d["kind"] == KIND_CANVAS else [],
    )


class PieriaPlacardButton(PieriaDisplayEntity, ButtonEntity):
    """Show the placard for the current artwork."""

    _attr_translation_key = "show_placard"

    def __init__(self, entry: PieriaConfigEntry, display_id: str) -> None:
        super().__init__(entry, display_id, "show_placard")

    async def async_press(self) -> None:
        """Show the placard."""
        await self.async_command("show_placard")
