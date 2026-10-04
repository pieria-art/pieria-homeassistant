"""Server-level quiet override switch."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import PieriaConfigEntry
from .entity import PieriaServerEntity, call_api

PARALLEL_UPDATES = 1

SERVICE_SET_QUIET = "set_quiet"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PieriaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the quiet switch and its service."""
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SET_QUIET,
        {
            vol.Required("on"): cv.boolean,
            vol.Optional("until"): cv.datetime,
            vol.Optional("duration"): cv.positive_time_period,
        },
        "async_set_quiet",
    )
    async_add_entities([PieriaQuietSwitch(entry)])


class PieriaQuietSwitch(PieriaServerEntity, SwitchEntity):
    """Manual quiet override: art off while on."""

    _attr_translation_key = "quiet"

    def __init__(self, entry: PieriaConfigEntry) -> None:
        super().__init__(entry, "quiet")

    @property
    def available(self) -> bool:
        """Needs /quiet (A2 servers)."""
        return super().available and self.coordinator.data.quiet is not None

    @property
    def is_on(self) -> bool | None:
        """Quiet is currently active (scheduled or manual)."""
        quiet = self.coordinator.data.quiet
        return bool(quiet["active"]) if quiet else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Why it is on, and until when."""
        quiet = self.coordinator.data.quiet or {}
        return {"source": quiet.get("source"), "until": quiet.get("until")}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Quiet on, until switched off."""
        await self.async_set_quiet(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Quiet off (overrides a schedule)."""
        await self.async_set_quiet(False)

    async def async_set_quiet(
        self,
        on: bool,
        until: datetime | None = None,
        duration: timedelta | None = None,
    ) -> None:
        """Set the manual quiet override."""
        if until is not None and duration is not None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="until_or_duration"
            )
        if duration is not None:
            until = dt_util.utcnow() + duration
        until_iso = dt_util.as_utc(until).isoformat() if until is not None else None
        await call_api("Pieria", self._api.set_quiet(on, until_iso))
        await self.coordinator.async_request_refresh()
