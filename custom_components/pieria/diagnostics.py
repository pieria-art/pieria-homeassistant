"""Diagnostics for Pieria."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_TOKEN
from .coordinator import PieriaConfigEntry

TO_REDACT = {CONF_TOKEN, CONF_HOST, "server_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PieriaConfigEntry
) -> dict[str, Any]:
    """Return diagnostics with the token redacted."""
    data = entry.runtime_data.coordinator.data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "info": async_redact_data(dict(entry.runtime_data.info), TO_REDACT),
        "displays": data.displays,
        "quiet": data.quiet,
        "playlists": [p["name"] for p in data.playlists],
    }
