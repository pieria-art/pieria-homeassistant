"""Coordinator, entities, commands, services."""

from __future__ import annotations

import copy
import json
from datetime import timedelta

import pytest
from homeassistant.components.media_player import ATTR_MEDIA_TITLE
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_PLAYING, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.pieria.const import DOMAIN

from .conftest import API, BASE, DISPLAYS, SERVER_ID, mock_server, setup_entry

MP = "media_player.living_room"
MP_EINK = "media_player.hall_eink"
QUIET = "switch.living_room_pi_quiet_mode"


def _posts(mock: AiohttpClientMocker, suffix: str) -> list:
    return [c for c in mock.mock_calls if c[0] == "POST" and str(c[1]).endswith(suffix)]


async def test_setup_entities_and_devices(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    await setup_entry(hass, mock_entry, aioclient_mock)
    assert mock_entry.state is ConfigEntryState.LOADED
    states = {s.entity_id for s in hass.states.async_all()}
    assert {
        MP,
        MP_EINK,
        "select.living_room_render_mode",
        "button.living_room_show_placard",
        "binary_sensor.living_room_online",
        "binary_sensor.hall_eink_online",
        "image.living_room_artwork",
        "image.hall_eink_artwork",
        QUIET,
    } <= states
    # canvas-only entities are not created for e-ink
    assert "select.hall_eink_render_mode" not in states
    assert "button.hall_eink_show_placard" not in states

    reg = dr.async_get(hass)
    server = reg.async_get_device({(DOMAIN, SERVER_ID)})
    assert server.name == "Living Room Pi"
    assert server.sw_version == "1.0.6"
    disp = reg.async_get_device({(DOMAIN, f"{SERVER_ID}_hall-eink")})
    assert disp.model == "eink"
    assert disp.via_device_id == server.id


async def test_media_player_state_mapping(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    await setup_entry(hass, mock_entry, aioclient_mock)
    state = hass.states.get(MP)
    assert state.state == STATE_PLAYING
    assert state.attributes[ATTR_MEDIA_TITLE] == "The Starry Night"
    assert state.attributes["media_artist"] == "Vincent van Gogh"
    assert state.attributes["source"] == "Impressionists"
    assert state.attributes["source_list"] == ["Impressionists", "Night"]
    assert state.attributes["entity_picture"]  # proxied: not remotely accessible
    assert hass.states.get(MP_EINK).state == STATE_OFF
    assert hass.states.get("binary_sensor.hall_eink_online").state == STATE_OFF
    assert hass.states.get("binary_sensor.living_room_online").state == STATE_ON

    entity = hass.data["media_player"].get_entity(MP)
    assert entity.media_image_url == f"{BASE}/media/42.jpg"
    assert entity.media_image_remotely_accessible is False


async def test_paused_state_and_refresh(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    await setup_entry(hass, mock_entry, aioclient_mock)
    paused = copy.deepcopy(DISPLAYS)
    paused[0]["paused"] = True
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/displays", json=paused)
    aioclient_mock.get(f"{API}/quiet", json={"active": False, "source": "none", "until": None})
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()
    assert hass.states.get(MP).state == "paused"


async def test_playlists_refreshed_less_often(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    await setup_entry(hass, mock_entry, aioclient_mock)
    for _ in range(3):
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11 * (_ + 1)))
        await hass.async_block_till_done()
    playlist_gets = [c for c in aioclient_mock.mock_calls if str(c[1]).endswith("/playlists")]
    assert len(playlist_gets) == 1


async def test_media_player_commands(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    await setup_entry(hass, mock_entry, aioclient_mock)
    path = f"{API}/displays/living-room/commands"
    aioclient_mock.post(path, status=202, json={"status": "queued"})
    for service, data, body in [
        ("media_pause", {}, {"action": "pause"}),
        ("media_play", {}, {"action": "resume"}),
        ("media_next_track", {}, {"action": "next"}),
        ("media_previous_track", {}, {"action": "previous"}),
        ("select_source", {"source": "Night"}, {"action": "set_playlist", "playlist": "Night"}),
    ]:
        aioclient_mock.mock_calls.clear()
        await hass.services.async_call(
            "media_player", service, {"entity_id": MP, **data}, blocking=True
        )
        posts = _posts(aioclient_mock, "/commands")
        assert len(posts) == 1
        assert posts[0][2] == body
        assert posts[0][3]["Authorization"] == "Bearer pieria_secret"


async def test_select_and_button(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    await setup_entry(hass, mock_entry, aioclient_mock)
    aioclient_mock.post(
        f"{API}/displays/living-room/commands", status=202, json={"status": "queued"}
    )
    assert hass.states.get("select.living_room_render_mode").state == "ken-burns"
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.living_room_render_mode", "option": "contain-matte"},
        blocking=True,
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.living_room_show_placard"}, blocking=True
    )
    bodies = [c[2] for c in _posts(aioclient_mock, "/commands")]
    assert bodies == [
        {"action": "set_mode", "mode": "contain-matte"},
        {"action": "show_placard"},
    ]


async def test_not_live_409_is_homeassistant_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    await setup_entry(hass, mock_entry, aioclient_mock)
    aioclient_mock.post(
        f"{API}/displays/hall-eink/commands",
        status=409,
        json={"error": {"code": "not_live", "message": "display is asleep"}},
    )
    with pytest.raises(HomeAssistantError) as exc:
        await hass.services.async_call(
            "media_player", "media_next_track", {"entity_id": MP_EINK}, blocking=True
        )
    assert exc.value.translation_key == "not_live"
    assert exc.value.translation_domain == DOMAIN


async def test_insufficient_scope_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    await setup_entry(hass, mock_entry, aioclient_mock)
    aioclient_mock.post(
        f"{API}/displays/living-room/commands",
        status=403,
        json={"error": {"code": "insufficient_scope", "message": "need control"}},
    )
    with pytest.raises(HomeAssistantError) as exc:
        await hass.services.async_call(
            "media_player", "media_pause", {"entity_id": MP}, blocking=True
        )
    assert exc.value.translation_key == "insufficient_scope"


async def test_quiet_switch(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    await setup_entry(
        hass,
        mock_entry,
        aioclient_mock,
        quiet={"active": True, "source": "schedule", "until": "2026-10-05T06:00:00Z"},
    )
    state = hass.states.get(QUIET)
    assert state.state == STATE_ON
    assert state.attributes["source"] == "schedule"
    assert state.attributes["until"] == "2026-10-05T06:00:00Z"

    aioclient_mock.post(f"{API}/quiet", json={"active": False, "source": "manual", "until": None})
    await hass.services.async_call("switch", "turn_off", {"entity_id": QUIET}, blocking=True)
    await hass.services.async_call("switch", "turn_on", {"entity_id": QUIET}, blocking=True)
    bodies = [c[2] for c in _posts(aioclient_mock, "/quiet")]
    assert bodies == [{"on": False, "until": None}, {"on": True, "until": None}]


async def test_quiet_switch_unavailable_without_quiet_endpoint(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    mock_entry.add_to_hass(hass)
    # first registered route wins, so the 404 goes in before the happy path
    aioclient_mock.get(
        f"{API}/quiet", status=404, json={"error": {"code": "not_found", "message": "no"}}
    )
    mock_server(aioclient_mock)
    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(QUIET).state == STATE_UNAVAILABLE
    assert hass.states.get(MP).state == STATE_PLAYING


async def test_set_quiet_service(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    await setup_entry(hass, mock_entry, aioclient_mock)
    aioclient_mock.post(f"{API}/quiet", json={"active": True, "source": "manual", "until": None})
    await hass.services.async_call(
        DOMAIN,
        "set_quiet",
        {"entity_id": QUIET, "on": True, "until": "2030-01-01T06:00:00+00:00"},
        blocking=True,
    )
    await hass.services.async_call(
        DOMAIN,
        "set_quiet",
        {"entity_id": QUIET, "on": True, "duration": {"hours": 2}},
        blocking=True,
    )
    first, second = (c[2] for c in _posts(aioclient_mock, "/quiet"))
    assert first == {"on": True, "until": "2030-01-01T06:00:00+00:00"}
    until = dt_util.parse_datetime(second["until"])
    delta = until - dt_util.utcnow()
    assert timedelta(hours=1, minutes=59) < delta <= timedelta(hours=2)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "set_quiet",
            {
                "entity_id": QUIET,
                "on": True,
                "until": "2030-01-01T06:00:00+00:00",
                "duration": {"hours": 1},
            },
            blocking=True,
        )


async def test_show_artwork_by_id_and_query(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    await setup_entry(hass, mock_entry, aioclient_mock)
    aioclient_mock.post(f"{API}/displays/living-room/show", status=202, json={"status": "queued"})
    aioclient_mock.get(f"{API}/search", json={"query": "water", "total": 1, "items": [{"id": 99}]})
    await hass.services.async_call(
        DOMAIN, "show_artwork", {"entity_id": MP, "artwork_id": 7}, blocking=True
    )
    await hass.services.async_call(
        DOMAIN, "show_artwork", {"entity_id": MP, "query": "water"}, blocking=True
    )
    assert [c[2] for c in _posts(aioclient_mock, "/show")] == [
        {"artwork_id": 7},
        {"artwork_id": 99},
    ]
    search = next(c for c in aioclient_mock.mock_calls if "/search" in str(c[1]))
    assert "q=water" in str(search[1])


async def test_show_artwork_validation(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    await setup_entry(hass, mock_entry, aioclient_mock)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "show_artwork", {"entity_id": MP}, blocking=True)
    aioclient_mock.get(f"{API}/search", json={"query": "zzz", "total": 0, "items": []})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "show_artwork", {"entity_id": MP, "query": "zzz"}, blocking=True
        )


async def test_show_artwork_not_live(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    await setup_entry(hass, mock_entry, aioclient_mock)
    aioclient_mock.post(
        f"{API}/displays/hall-eink/show",
        status=409,
        json={"error": {"code": "not_live", "message": "asleep"}},
    )
    with pytest.raises(HomeAssistantError) as exc:
        await hass.services.async_call(
            DOMAIN, "show_artwork", {"entity_id": MP_EINK, "artwork_id": 1}, blocking=True
        )
    assert exc.value.translation_key == "not_live"


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    mock_entry.add_to_hass(hass)
    aioclient_mock.get(
        f"{API}/info", status=401, json={"error": {"code": "unauthorized", "message": "x"}}
    )
    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_entry.state is ConfigEntryState.SETUP_ERROR
    assert any(
        f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress()
    )


async def test_server_down_retries(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    mock_entry.add_to_hass(hass)
    aioclient_mock.get(f"{API}/info", exc=TimeoutError)
    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_entry.state is ConfigEntryState.SETUP_RETRY


async def test_diagnostics_redacts_token(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    from custom_components.pieria.diagnostics import async_get_config_entry_diagnostics

    await setup_entry(hass, mock_entry, aioclient_mock)
    diag = await async_get_config_entry_diagnostics(hass, mock_entry)
    assert "pieria_secret" not in json.dumps(diag)
    assert diag["entry"]["token"] == "**REDACTED**"
    assert "living-room" in diag["displays"]


async def test_unload(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry) -> None:
    await setup_entry(hass, mock_entry, aioclient_mock)
    await hass.config_entries.async_unload(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_entry.state is ConfigEntryState.NOT_LOADED
