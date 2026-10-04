"""Render-mode select (canvas displays only)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import KIND_CANVAS, RENDER_MODES
from .coordinator import PieriaConfigEntry
from .entity import PieriaDisplayEntity, setup_display_entities

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PieriaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up selects."""
    setup_display_entities(
        entry,
        async_add_entities,
        lambda e, d: [PieriaRenderMode(e, d["id"])] if d["kind"] == KIND_CANVAS else [],
    )


class PieriaRenderMode(PieriaDisplayEntity, SelectEntity):
    """How artwork is rendered on the canvas."""

    _attr_translation_key = "render_mode"
    _attr_options = RENDER_MODES

    def __init__(self, entry: PieriaConfigEntry, display_id: str) -> None:
        super().__init__(entry, display_id, "render_mode")

    @property
    def current_option(self) -> str | None:
        """Current mode."""
        display = self.display
        mode = display.get("mode") if display else None
        return mode if mode in RENDER_MODES else None

    async def async_select_option(self, option: str) -> None:
        """Change mode."""
        await self.async_command("set_mode", mode=option)
