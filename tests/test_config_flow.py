"""Config flow tests."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.pieria.const import CONF_SCAN_INTERVAL, CONF_TOKEN, DOMAIN

from .conftest import API, HOST, INFO, PORT, SERVER_ID, mock_server, setup_entry


def _zeroconf(host: str = HOST) -> ZeroconfServiceInfo:
    return ZeroconfServiceInfo(
        ip_address=host,
        ip_addresses=[host],
        hostname="pieria.local.",
        name="Pieria._pieria._tcp.local.",
        port=PORT,
        type="_pieria._tcp.local.",
        properties={"version": "1.0.6", "server_id": SERVER_ID, "path": "/api/v1"},
    )


async def test_manual_flow(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    mock_server(aioclient_mock)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_PORT: PORT}
    )
    assert result["step_id"] == "token"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "pieria_abc"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Living Room Pi"
    assert result["data"] == {CONF_HOST: HOST, CONF_PORT: PORT, CONF_TOKEN: "pieria_abc"}
    assert result["result"].unique_id == SERVER_ID
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == "Bearer pieria_abc"


async def test_zeroconf_flow(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    mock_server(aioclient_mock)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=_zeroconf()
    )
    assert result["step_id"] == "discovery_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "token"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "pieria_abc"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == HOST


async def test_zeroconf_already_configured_updates_host(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    await setup_entry(hass, mock_entry, aioclient_mock)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zeroconf("192.0.2.77"),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_entry.data[CONF_HOST] == "192.0.2.77"


async def test_manual_already_configured(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    await setup_entry(hass, mock_entry, aioclient_mock)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_PORT: PORT}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "pieria_abc"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_invalid_auth_then_recover(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(
        f"{API}/info",
        status=401,
        json={"error": {"code": "unauthorized", "message": "bad token"}},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_PORT: PORT}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_TOKEN: "nope"})
    assert result["errors"] == {"base": "invalid_auth"}
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/info", json=INFO)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "pieria_ok"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_cannot_connect(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{API}/info", exc=TimeoutError)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_PORT: PORT}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_TOKEN: "x"})
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry) -> None:
    await setup_entry(hass, mock_entry, aioclient_mock)
    result = await mock_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    aioclient_mock.clear_requests()
    mock_server(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "pieria_new"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_entry.data[CONF_TOKEN] == "pieria_new"


async def test_reauth_wrong_server(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    await setup_entry(hass, mock_entry, aioclient_mock)
    result = await mock_entry.start_reauth_flow(hass)
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/info", json={**INFO, "server_id": "other"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "pieria_new"}
    )
    assert result["reason"] == "wrong_server"


async def test_options_flow(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_entry
) -> None:
    await setup_entry(hass, mock_entry, aioclient_mock)
    assert mock_entry.runtime_data.coordinator.update_interval.total_seconds() == 10
    result = await hass.config_entries.options.async_init(mock_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 30}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert mock_entry.options[CONF_SCAN_INTERVAL] == 30
    assert mock_entry.runtime_data.coordinator.update_interval.total_seconds() == 30
