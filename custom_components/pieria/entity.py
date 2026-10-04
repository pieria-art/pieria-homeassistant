"""Shared entity helpers."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Display, PieriaApiError, PieriaAuthError, PieriaConnectionError
from .const import DOMAIN
from .coordinator import PieriaConfigEntry, PieriaCoordinator


def server_device_info(entry: PieriaConfigEntry) -> DeviceInfo:
    """Device info for the Pieria server."""
    info = entry.runtime_data.info
    return DeviceInfo(
        identifiers={(DOMAIN, info["server_id"])},
        name=info.get("display_name") or "Pieria",
        manufacturer="Pieria",
        model="Pieria server",
        sw_version=info["version"],
        configuration_url=entry.runtime_data.client.base_url,
    )


def register_display_device(
    hass: HomeAssistant, entry: PieriaConfigEntry, display: Display
) -> None:
    """Create the display's device linked to the server device.

    Newer Home Assistant wants via_device_id (via_device is deprecated, removed 2027.8); older
    releases only know via_device. Pick whichever async_get_or_create supports.
    """
    registry = dr.async_get(hass)
    server_id = entry.runtime_data.info["server_id"]
    server = registry.async_get_device(identifiers={(DOMAIN, server_id)})
    params = inspect.signature(registry.async_get_or_create).parameters
    via: dict[str, Any]
    if "via_device_id" in params:
        via = {"via_device_id": server.id if server else None}
    else:
        via = {"via_device": (DOMAIN, server_id)}
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{server_id}_{display['id']}")},
        name=display.get("name") or display["id"],
        manufacturer="Pieria",
        model=display.get("kind", "unknown"),
        **via,
    )


async def call_api(display_name: str, coro: Awaitable[Any]) -> Any:
    """Await an API call, mapping client errors to translated HA errors."""
    try:
        return await coro
    except PieriaAuthError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="insufficient_scope"
            if err.code == "insufficient_scope"
            else "auth_failed",
        ) from err
    except PieriaConnectionError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="cannot_connect"
        ) from err
    except PieriaApiError as err:
        key = {
            "not_live": "not_live",
            "unknown_playlist": "unknown_playlist",
            "unsupported_for_kind": "unsupported_for_kind",
            "not_found": "not_found",
        }.get(err.code, "api_error")
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key=key,
            translation_placeholders={"display": display_name, "message": err.message or err.code},
        ) from err


class PieriaServerEntity(CoordinatorEntity[PieriaCoordinator]):
    """Entity on the server device."""

    _attr_has_entity_name = True

    def __init__(self, entry: PieriaConfigEntry, key: str) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self._entry = entry
        self._api = entry.runtime_data.client
        server_id = entry.runtime_data.info["server_id"]
        self._attr_unique_id = f"{server_id}_{key}"
        self._attr_device_info = server_device_info(entry)


class PieriaDisplayEntity(CoordinatorEntity[PieriaCoordinator]):
    """Entity on a display device."""

    _attr_has_entity_name = True

    def __init__(self, entry: PieriaConfigEntry, display_id: str, key: str) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self._entry = entry
        self._api = entry.runtime_data.client
        self.display_id = display_id
        server_id = entry.runtime_data.info["server_id"]
        self._attr_unique_id = f"{server_id}_{display_id}_{key}"
        kind = (self.display or {}).get("kind", "unknown")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{server_id}_{display_id}")},
            name=(self.display or {}).get("name") or display_id,
            manufacturer="Pieria",
            model=kind,
        )

    @property
    def display(self) -> Display | None:
        """Latest snapshot of this display."""
        return self.coordinator.data.displays.get(self.display_id)

    @property
    def available(self) -> bool:
        """Available while the server answers and still lists this display."""
        return super().available and self.display is not None

    async def async_command(
        self, action: str, patch: dict[str, Any] | None = None, **kwargs: Any
    ) -> None:
        """Send a command, show the expected state, and refresh."""
        await call_api(self.display_id, self._api.command(self.display_id, action, **kwargs))
        await self.coordinator.async_after_command(self.display_id, patch)


@callback
def setup_display_entities(
    entry: PieriaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[PieriaConfigEntry, Display], list[PieriaDisplayEntity]],
) -> None:
    """Add entities for each display, including ones that appear later.

    The factory is re-run on every update so kind-gated entities appear once a display's
    kind is known; entities already added (by unique id) are skipped.
    """
    coordinator = entry.runtime_data.coordinator
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new: list[PieriaDisplayEntity] = []
        for display in coordinator.data.displays.values():
            register_display_device(coordinator.hass, entry, display)
            for entity in factory(entry, display):
                if entity.unique_id in known:
                    continue
                known.add(entity.unique_id)
                new.append(entity)
        if new:
            async_add_entities(new)

    entry.async_on_unload(coordinator.async_add_listener(_add_new))
    _add_new()
