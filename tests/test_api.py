"""API client tests (no Home Assistant entities)."""

from __future__ import annotations

import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.pieria.api import (
    PieriaApiError,
    PieriaAuthError,
    PieriaClient,
    PieriaConnectionError,
)

from .conftest import API, HOST, PORT


async def _client(hass) -> PieriaClient:
    return PieriaClient(async_get_clientsession(hass), HOST, PORT, "tok")


async def test_error_envelope_mapping(hass, aioclient_mock: AiohttpClientMocker) -> None:
    client = await _client(hass)
    aioclient_mock.get(
        f"{API}/artworks/1", status=404, json={"error": {"code": "not_found", "message": "m"}}
    )
    with pytest.raises(PieriaApiError) as exc:
        await client.artwork(1)
    assert exc.value.code == "not_found"
    assert not isinstance(exc.value, PieriaAuthError)

    aioclient_mock.get(
        f"{API}/info", status=403, json={"error": {"code": "insufficient_scope", "message": "m"}}
    )
    with pytest.raises(PieriaAuthError) as auth:
        await client.info()
    assert auth.value.code == "insufficient_scope"

    aioclient_mock.get(f"{API}/schedule", status=500, text="boom")
    with pytest.raises(PieriaApiError) as other:
        await client.get_schedule()
    assert other.value.code == "http_500"


async def test_connection_error(hass, aioclient_mock: AiohttpClientMocker) -> None:
    client = await _client(hass)
    aioclient_mock.get(f"{API}/info", exc=TimeoutError)
    with pytest.raises(PieriaConnectionError):
        await client.info()


async def test_schedule_patch_and_ipv6_base(hass, aioclient_mock: AiohttpClientMocker) -> None:
    client = await _client(hass)
    aioclient_mock.patch(f"{API}/schedule", json={"enabled": True})
    await client.patch_schedule(enabled=True)
    assert aioclient_mock.mock_calls[0][2] == {"enabled": True}
    v6 = PieriaClient(async_get_clientsession(hass), "fe80::1", 80, "t")
    assert v6.base_url == "http://[fe80::1]:80"
    assert v6.absolute_url("/media/a.jpg") == "http://[fe80::1]:80/media/a.jpg"


async def test_command_playlist_id_and_quiet_body(
    hass, aioclient_mock: AiohttpClientMocker
) -> None:
    client = await _client(hass)
    aioclient_mock.post(f"{API}/displays/d/commands", status=202, json={"status": "queued"})
    aioclient_mock.post(f"{API}/quiet", json={"active": True, "mode": "on", "source": "manual"})
    await client.command("d", "set_playlist", playlist_id=3)
    quiet = await client.set_quiet("on", "2030-01-01T00:00:00+00:00")
    await client.set_quiet("auto", "2030-01-01T00:00:00+00:00")
    assert aioclient_mock.mock_calls[0][2] == {"action": "set_playlist", "playlist_id": 3}
    assert aioclient_mock.mock_calls[1][2] == {"mode": "on", "until": "2030-01-01T00:00:00+00:00"}
    assert aioclient_mock.mock_calls[2][2] == {"mode": "auto"}
    assert quiet["mode"] == "on"
