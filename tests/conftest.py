"""Shared fixtures."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.pieria.const import CONF_TOKEN, DOMAIN

HOST = "192.0.2.10"
PORT = 8000
BASE = f"http://{HOST}:{PORT}"
API = f"{BASE}/api/v1"
SERVER_ID = "7d1f8a52-0000-4000-8000-000000000001"

INFO = {
    "name": "Pieria",
    "version": "1.0.6",
    "api_version": 1,
    "appliance_mode": True,
    "server_id": SERVER_ID,
    "display_name": "Living Room Pi",
}

ARTWORK = {
    "id": 42,
    "title": "The Starry Night",
    "artist": "Vincent van Gogh",
    "year": "1889",
    "image_url": "/media/42.jpg",
    "thumb_url": "/media/42_t.jpg",
    "is_personal": False,
}

DISPLAYS = [
    {
        "id": "living-room",
        "live": True,
        "last_seen": "2026-10-04T10:00:00Z",
        "kind": "canvas",
        "playlist": "Impressionists",
        "paused": False,
        "mode": "ken-burns",
        "artwork": ARTWORK,
    },
    {
        "id": "hall-eink",
        "live": False,
        "last_seen": "2026-10-04T08:00:00Z",
        "kind": "eink",
        "playlist": None,
        "paused": False,
        "mode": None,
        "artwork": None,
    },
]

PLAYLISTS = [
    {
        "id": 1,
        "name": "Impressionists",
        "artwork_count": 10,
        "display_time": 60,
        "shuffle": True,
        "default_mode": "ken-burns",
        "is_personal": False,
    },
    {
        "id": 2,
        "name": "Night",
        "artwork_count": 5,
        "display_time": 120,
        "shuffle": False,
        "default_mode": "contain-matte",
        "is_personal": False,
    },
]

QUIET_OFF = {"active": False, "source": "none", "until": None}


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow loading custom_components."""


def mock_server(
    mock: AiohttpClientMocker,
    *,
    displays: list[dict[str, Any]] | None = None,
    quiet: dict[str, Any] | None = None,
) -> None:
    """Register the happy-path GET routes."""
    mock.get(f"{API}/info", json=INFO)
    mock.get(f"{API}/displays", json=copy.deepcopy(displays if displays is not None else DISPLAYS))
    mock.get(f"{API}/playlists", json=PLAYLISTS)
    mock.get(f"{API}/quiet", json=quiet or QUIET_OFF)


@pytest.fixture
def mock_entry() -> MockConfigEntry:
    """A config entry for the test server."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=SERVER_ID,
        title="Living Room Pi",
        data={CONF_HOST: HOST, CONF_PORT: PORT, CONF_TOKEN: "pieria_secret"},
    )


async def setup_entry(
    hass: HomeAssistant, entry: MockConfigEntry, mock: AiohttpClientMocker, **kw: Any
) -> MockConfigEntry:
    """Mock the server and set the entry up."""
    mock_server(mock, **kw)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
