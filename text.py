"""Søkefelt i HA: skriv hva du leter etter, så svarer sensoren «Søkesvar» hvor det ligger."""
from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .api import TingstedError
from .entity import TingstedEntity
from .helpers import SIGNAL_SEARCH


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([SearchText(entry)])


class SearchText(TingstedEntity, TextEntity):
    _attr_icon = "mdi:magnify"
    _attr_native_max = 100

    def __init__(self, entry) -> None:
        super().__init__(entry, "search")
        self._entry = entry

    @property
    def native_value(self) -> str:
        return self._entry.runtime_data.search.get("query", "")

    async def async_set_value(self, value: str) -> None:
        q = (value or "").strip()
        data = self._entry.runtime_data
        if not q:
            data.search = {}
        else:
            try:
                where = await data.client.where(q)
                res = await data.client.search(q)
                data.search = {"query": q, "speech": where.get("speech", ""), "found": where.get("found", False),
                               "results": res.get("results", [])}
            except TingstedError as e:
                data.search = {"query": q, "speech": f"Tingsted svarte ikke: {e}", "found": False, "results": []}
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, SIGNAL_SEARCH.format(self._entry.entry_id))
