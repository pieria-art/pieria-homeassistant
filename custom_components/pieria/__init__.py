"""The Pieria integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PieriaAuthError, PieriaClient, PieriaError
from .const import CONF_TOKEN
from .coordinator import PieriaConfigEntry, PieriaCoordinator, PieriaRuntimeData
from .entity import server_device_info
from .scopes import missing_scope

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.IMAGE,
    Platform.MEDIA_PLAYER,
    Platform.SELECT,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: PieriaConfigEntry) -> bool:
    """Set up Pieria from a config entry."""
    client = PieriaClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_TOKEN],
    )
    try:
        info = await client.info()
    except PieriaAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except PieriaError as err:
        raise ConfigEntryNotReady(str(err)) from err

    if missing_scope(info):
        raise ConfigEntryAuthFailed("token lacks the read or control scope")

    coordinator = PieriaCoordinator(hass, entry, client, frozenset(info.get("api_features") or []))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = PieriaRuntimeData(client=client, coordinator=coordinator, info=info)

    # Register the server device first so display devices can name it as via_device.
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **server_device_info(entry)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: PieriaConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: PieriaConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
