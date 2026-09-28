"""Oppsett: adressen til Tingsted og en API-nøkkel."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TingstedAuthError, TingstedClient, TingstedError
from .const import CONF_KEY, CONF_SCAN, CONF_URL, DEFAULT_SCAN, DOMAIN


async def _check(hass, url: str, key: str) -> tuple[dict | None, str | None]:
    if not urlparse(url).scheme.startswith("http"):
        return None, "invalid_url"
    if not key.strip().startswith("tsk_"):
        return None, "invalid_key"
    try:
        return await TingstedClient(async_get_clientsession(hass), url, key).info(), None
    except TingstedAuthError:
        return None, "invalid_auth"
    except TingstedError:
        return None, "cannot_connect"


class TingstedConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].strip().rstrip("/")
            info, err = await _check(self.hass, url, user_input[CONF_KEY])
            if err:
                errors["base"] = err
            else:
                hh = info["household"]
                await self.async_set_unique_id(f"{urlparse(url).netloc}-{hh['id']}")
                self._abort_if_unique_id_configured(updates={CONF_URL: url, CONF_KEY: user_input[CONF_KEY].strip()})
                return self.async_create_entry(title=hh["name"], data={CONF_URL: url, CONF_KEY: user_input[CONF_KEY].strip()})
        schema = vol.Schema({
            vol.Required(CONF_URL, default=(user_input or {}).get(CONF_URL, "http://")): str,
            vol.Required(CONF_KEY): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            info, err = await _check(self.hass, entry.data[CONF_URL], user_input[CONF_KEY])
            if err:
                errors["base"] = err
            else:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_KEY: user_input[CONF_KEY].strip()})
        return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({vol.Required(CONF_KEY): str}),
                                    errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return TingstedOptionsFlow()


class TingstedOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        cur = self.config_entry.options.get(CONF_SCAN, DEFAULT_SCAN)
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required(CONF_SCAN, default=cur): vol.All(vol.Coerce(int), vol.Range(min=30, max=86400)),
        }))
