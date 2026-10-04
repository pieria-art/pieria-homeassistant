"""Render-mode select (canvas displays only) and the server's quiet-mode select."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import FEATURE_QUIET, KIND_CANVAS, QUIET_MODES, RENDER_MODES
from .coordinator import PieriaConfigEntry
from .entity import PieriaDisplayEntity, PieriaServerEntity, call_api, setup_display_entities

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PieriaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up selects."""
    if FEATURE_QUIET in entry.runtime_data.coordinator.features:
        async_add_entities([PieriaQuietSelect(entry)])
    setup_display_entities(
        entry,
        async_add_entities,
        lambda e, d: [PieriaRenderMode(e, d["id"])] if d["kind"] == KIND_CANVAS else [],
    )


class PieriaQuietSelect(PieriaServerEntity, SelectEntity):
    """Explicit quiet override: auto follows the schedule, on / off force it."""

    _attr_translation_key = "quiet_mode"
    _attr_options = QUIET_MODES

    def __init__(self, entry: PieriaConfigEntry) -> None:
        super().__init__(entry, "quiet_mode")

    @property
    def available(self) -> bool:
        """Needs a readable /quiet."""
        return super().available and self.coordinator.data.quiet is not None

    @property
    def current_option(self) -> str | None:
        """The override in force."""
        quiet = self.coordinator.data.quiet
        mode = quiet.get("mode") if quiet else None
        return mode if mode in QUIET_MODES else None

    async def async_select_option(self, option: str) -> None:
        """Set the override (on / off end at the next schedule boundary)."""
        quiet = await call_api("Pieria", self._api.set_quiet(option))
        self.coordinator.set_quiet_state(quiet)
        await self.coordinator.async_request_refresh()


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
        await self.async_command("set_mode", {"mode": option}, mode=option)
