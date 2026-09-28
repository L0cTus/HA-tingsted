"""Viser hendelser fra Tingsted i aktivitetsloggen (også på enhetssiden)."""
from __future__ import annotations

from homeassistant.components.logbook import LOGBOOK_ENTRY_ENTITY_ID, LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, EVENT


def _text(d: dict) -> str:
    ev, name, box = d.get("event", ""), d.get("name") or "", d.get("box") or d.get("code") or ""
    return {
        "item.added": f"la til «{name}»" + (f" i {box}" if box else ""),
        "item.updated": f"endret «{name}»",
        "item.deleted": f"fjernet «{name}»",
        "item.lent": f"lånte ut «{name}» til {d.get('lent_to', '')}",
        "item.returned": f"fikk «{name}» tilbake fra {d.get('lent_to', '')}",
        "box.created": f"laget kasse {d.get('path') or box}",
        "box.moved": f"flyttet {d.get('code', '')} til {d.get('new', '')}",
        "box.deleted": f"slettet kasse {d.get('path') or box}",
        "ai.done": f"AI-forslag er klare ({d.get('items', 0)} ting)",
        "test": "testmelding fra Tingsted",
    }.get(ev, ev)


@callback
def async_describe_events(hass, async_describe_event) -> None:
    @callback
    def describe(event) -> dict:
        d = event.data
        out = {LOGBOOK_ENTRY_NAME: f"Tingsted {d.get('household', '')}".strip(), LOGBOOK_ENTRY_MESSAGE: _text(d)}
        entry = hass.config_entries.async_get_entry(d.get("config_entry_id", ""))
        if entry:
            eid = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{entry.unique_id or entry.entry_id}_items")
            if eid:
                out[LOGBOOK_ENTRY_ENTITY_ID] = eid      # så den vises under Aktivitet på enheten
        return out

    async_describe_event(DOMAIN, EVENT, describe)
