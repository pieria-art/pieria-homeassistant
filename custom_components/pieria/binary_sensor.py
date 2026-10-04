"""Online (live) binary sensor."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PieriaConfigEntry
from .entity import PieriaDisplayEntity, setup_display_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PieriaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    setup_display_entities(entry, async_add_entities, lambda e, d: [PieriaOnline(e, d["id"])])


class PieriaOnline(PieriaDisplayEntity, BinarySensorEntity):
    """Display is checking in."""

    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, entry: PieriaConfigEntry, display_id: str) -> None:
        super().__init__(entry, display_id, "online")

    @property
    def is_on(self) -> bool | None:
        """True when live."""
        display = self.display
        return bool(display["live"]) if display else None
