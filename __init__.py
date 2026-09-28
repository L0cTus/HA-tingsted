"""Tingsted for Home Assistant: sensorer, utlånsliste, tjenester, «Hvor er …?» og hendelser fra Tingsted."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import voluptuous as vol
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import intent
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TingstedAuthError, TingstedClient, TingstedError, verify_signature
from .const import CONF_KEY, CONF_SCAN, CONF_URL, DEFAULT_SCAN, DOMAIN, EVENT
from .helpers import SIGNAL_EVENT, event_text

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.TODO, Platform.TEXT, Platform.BUTTON, Platform.CALENDAR]
CARD_URL = "/tingsted_static"
CARD_VERSION = "0.3.0"
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class TingstedData:
    client: TingstedClient
    coordinator: "TingstedCoordinator"
    info: dict
    search: dict = field(default_factory=dict)       # siste søk fra søkefeltet
    last_event: dict = field(default_factory=dict)   # siste hendelse fra webhooken

    @property
    def can_write(self) -> bool:
        return self.info.get("key", {}).get("role") == "write"


TingstedConfigEntry = ConfigEntry  # ConfigEntry[TingstedData]


class TingstedCoordinator(DataUpdateCoordinator[dict]):
    """Henter tall og utlånsliste. Webhooken ber om ny henting når noe skjer."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: TingstedClient) -> None:
        super().__init__(hass, _LOGGER, name=f"Tingsted {entry.title}", config_entry=entry,
                         update_interval=timedelta(seconds=entry.options.get(CONF_SCAN, DEFAULT_SCAN)))
        self.client = client

    async def _async_update_data(self) -> dict:
        try:
            data = {"stats": await self.client.stats(), "lent": await self.client.lent()}
            try:
                data["values"] = await self.client.values()
            except TingstedError:
                data["values"] = {}          # eldre Tingsted uten /values
            return data
        except TingstedAuthError as e:
            raise ConfigEntryAuthFailed(str(e)) from e
        except TingstedError as e:
            raise UpdateFailed(str(e)) from e


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Tjenester og «Hvor er …?» registreres én gang, uansett hvor mange husstander som er koblet til."""
    _register_services(hass)
    intent.async_register(hass, FindIntent())
    await _register_card(hass)
    return True


async def _register_card(hass: HomeAssistant) -> None:
    """Gjør «custom:tingsted-card» tilgjengelig i dashbordene, uten at du må legge til en ressurs selv."""
    try:
        from homeassistant.components.frontend import add_extra_js_url
        from homeassistant.components.http import StaticPathConfig
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(Path(__file__).parent / "www"), False)])
        add_extra_js_url(hass, f"{CARD_URL}/tingsted-card.js?v={CARD_VERSION}")
    except Exception as e:  # kortet er et tillegg; integrasjonen virker uten
        _LOGGER.warning("Tingsted: kunne ikke registrere kortet: %s", e)


async def async_setup_entry(hass: HomeAssistant, entry: TingstedConfigEntry) -> bool:
    client = TingstedClient(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_KEY])
    try:
        info = await client.info()
    except TingstedAuthError as e:
        raise ConfigEntryAuthFailed(str(e)) from e
    except TingstedError as e:
        raise ConfigEntryNotReady(str(e)) from e
    coordinator = TingstedCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = TingstedData(client=client, coordinator=coordinator, info=info)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if entry.runtime_data.can_write:
        await _setup_webhook(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_reload_on_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TingstedConfigEntry) -> bool:
    if entry.data.get("webhook_id"):
        webhook.async_unregister(hass, entry.data["webhook_id"])
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Integrasjonen fjernes: slett webhooken i Tingsted også."""
    if entry.data.get("remote_hook_id"):
        client = TingstedClient(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_KEY])
        try:
            await client.delete_webhook(entry.data["remote_hook_id"])
        except TingstedError:
            pass


async def _reload_on_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


# ---------------------------------------------------------------- webhook (Tingsted -> HA)
async def _setup_webhook(hass: HomeAssistant, entry: TingstedConfigEntry) -> None:
    """Registrerer en webhook i HA og ber Tingsted sende hendelser dit. Da oppdateres alt med en gang."""
    wid = entry.data.get("webhook_id") or webhook.async_generate_id()
    try:
        base = get_url(hass, allow_cloud=False, prefer_external=False)
    except NoURLAvailableError:
        _LOGGER.warning("Tingsted: fant ingen intern adresse for Home Assistant, så det blir bare jevnlig henting")
        return
    url = f"{base}/api/webhook/{wid}"
    data = dict(entry.data)
    if data.get("webhook_url") != url or not data.get("hook_secret"):
        try:
            hook = await entry.runtime_data.client.create_webhook(url)
        except TingstedError as e:
            _LOGGER.warning("Tingsted: kunne ikke sette opp webhook (%s). Bruker jevnlig henting", e)
            return
        data.update(webhook_id=wid, webhook_url=url, remote_hook_id=hook["id"], hook_secret=hook["secret"])
        hass.config_entries.async_update_entry(entry, data=data)
    webhook.async_register(hass, DOMAIN, f"Tingsted {entry.title}", wid, _make_handler(entry), local_only=True,
                           allowed_methods=["POST"])


def _make_handler(entry: TingstedConfigEntry):
    async def handle(hass: HomeAssistant, webhook_id: str, request):
        body = await request.read()
        if not verify_signature(entry.data.get("hook_secret", ""), body, request.headers.get("X-Tingsted-Signature")):
            _LOGGER.warning("Tingsted: webhook med feil signatur ble avvist")
            return None
        try:
            payload = await request.json()
        except ValueError:
            return None
        name = str(payload.get("event", ""))
        data = {"event": name, "household": entry.title, "config_entry_id": entry.entry_id, **(payload.get("data") or {})}
        hass.bus.async_fire(EVENT, data)
        if name != "test":
            entry.runtime_data.last_event = {**data, "text": event_text(data)}
            async_dispatcher_send(hass, SIGNAL_EVENT.format(entry.entry_id))
        if name and name != "test":
            hass.bus.async_fire(f"{DOMAIN}_{name.replace('.', '_')}", data)
        await entry.runtime_data.coordinator.async_request_refresh()
        return None
    return handle


# ---------------------------------------------------------------- tjenester
def _entry(hass: HomeAssistant, entry_id: str | None) -> TingstedConfigEntry:
    entries = [e for e in hass.config_entries.async_loaded_entries(DOMAIN)] if hasattr(hass.config_entries, "async_loaded_entries") \
        else [e for e in hass.config_entries.async_entries(DOMAIN) if getattr(e, "runtime_data", None)]
    if entry_id:
        entries = [e for e in entries if e.entry_id == entry_id]
    if not entries:
        raise HomeAssistantError("Tingsted er ikke satt opp")
    return entries[0]


def _register_services(hass: HomeAssistant) -> None:
    entry_field = vol.Optional("config_entry_id")

    async def find(call: ServiceCall) -> ServiceResponse:
        e = _entry(hass, call.data.get("config_entry_id"))
        try:
            return await e.runtime_data.client.where(call.data["query"])
        except TingstedError as err:
            raise HomeAssistantError(str(err)) from err

    async def search(call: ServiceCall) -> ServiceResponse:
        e = _entry(hass, call.data.get("config_entry_id"))
        try:
            return await e.runtime_data.client.search(call.data["query"])
        except TingstedError as err:
            raise HomeAssistantError(str(err)) from err

    async def recent(call: ServiceCall) -> ServiceResponse:
        e = _entry(hass, call.data.get("config_entry_id"))
        try:
            return await e.runtime_data.client.history(int(call.data.get("limit", 15)))
        except TingstedError as err:
            raise HomeAssistantError(str(err)) from err

    async def add_items(call: ServiceCall) -> ServiceResponse:
        e = _entry(hass, call.data.get("config_entry_id"))
        items = call.data["items"]
        items = [items] if isinstance(items, str) else list(items)
        try:
            res = await e.runtime_data.client.add_items(call.data["box"], items)
        except TingstedError as err:
            raise HomeAssistantError(str(err)) from err
        await e.runtime_data.coordinator.async_request_refresh()
        return res

    async def lend(call: ServiceCall) -> None:
        e = _entry(hass, call.data.get("config_entry_id"))
        fields = {"lent_to": call.data["to"]}
        if call.data.get("due"):
            from datetime import datetime, time as dtime
            fields["lent_due"] = datetime.combine(call.data["due"], dtime(23, 59)).timestamp()
        try:
            await e.runtime_data.client.update_item(call.data["item_id"], **fields)
        except TingstedError as err:
            raise HomeAssistantError(str(err)) from err
        await e.runtime_data.coordinator.async_request_refresh()

    async def return_item(call: ServiceCall) -> None:
        e = _entry(hass, call.data.get("config_entry_id"))
        try:
            await e.runtime_data.client.return_item(call.data["item_id"])
        except TingstedError as err:
            raise HomeAssistantError(str(err)) from err
        await e.runtime_data.coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, "find", find, vol.Schema({vol.Required("query"): cv.string, entry_field: cv.string}),
                                 supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "search", search, vol.Schema({vol.Required("query"): cv.string, entry_field: cv.string}),
                                 supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "recent", recent, vol.Schema({vol.Optional("limit"): vol.Coerce(int), entry_field: cv.string}),
                                 supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "add_items", add_items, vol.Schema({
        vol.Required("box"): cv.string, vol.Required("items"): vol.Any(cv.string, [cv.string]), entry_field: cv.string}),
        supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "lend", lend, vol.Schema({
        vol.Required("item_id"): vol.Coerce(int), vol.Required("to"): cv.string, vol.Optional("due"): cv.date, entry_field: cv.string}))
    hass.services.async_register(DOMAIN, "return_item", return_item, vol.Schema({
        vol.Required("item_id"): vol.Coerce(int), entry_field: cv.string}))


# ---------------------------------------------------------------- «Hvor er …?» i Assist
class FindIntent(intent.IntentHandler):
    """Svarer på «hvor er skjøteledningen?». Setningene ligger i custom_sentences/nb/tingsted.yaml."""

    intent_type = "TingstedFind"
    description = "Finds where a physical item is stored at home (which box, shelf and room) using Tingsted"
    slot_schema = {vol.Required("item"): cv.string}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        slots = self.async_validate_slots(intent_obj.slots)
        item = slots["item"]["value"].strip(" ?.!")
        response = intent_obj.create_response()
        try:
            e = _entry(intent_obj.hass, None)
            res = await e.runtime_data.client.where(item)
            response.async_set_speech(res.get("speech") or f"Jeg fant ikke {item}.")
        except (TingstedError, HomeAssistantError) as err:
            response.async_set_speech(f"Tingsted svarte ikke: {err}")
        return response
