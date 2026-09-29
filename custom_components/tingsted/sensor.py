"""Sensorer: kasser, ting, steder, utlånt, over fristen og AI-kø."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .entity import TingstedEntity
from .helpers import SIGNAL_EVENT, SIGNAL_SEARCH


@dataclass(frozen=True)
class Spec:
    key: str
    stat: str
    icon: str
    default_on: bool = True


SPECS = [
    Spec("boxes", "boxes", "mdi:package-variant-closed"),
    Spec("items", "items", "mdi:format-list-bulleted"),
    Spec("items_total", "items_total", "mdi:counter", False),
    Spec("places", "places", "mdi:home-city-outline"),
    Spec("shelves", "shelves", "mdi:bookshelf", False),
    Spec("lent", "lent", "mdi:hand-extended-outline"),
    Spec("lent_overdue", "lent_overdue", "mdi:clock-alert-outline", False),
    Spec("ai_queue", "ai_queue", "mdi:robot-outline", False),
]


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    stats = entry.runtime_data.coordinator.data.get("stats", {})
    ents = [StatSensor(entry, s) for s in SPECS if not (s.key == "ai_queue" and stats.get("ai_queue") is None)]
    ents += [ValueSensor(entry), SearchResult(entry), LastEvent(entry)]
    async_add_entities(ents)


class ValueSensor(TingstedEntity, SensorEntity):
    """Samlet verdi av det som er registrert med verdi (til forsikringen)."""
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "NOK"
    _attr_icon = "mdi:cash-multiple"

    def __init__(self, entry) -> None:
        super().__init__(entry, "total_value")

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("values", {}).get("total")

    @property
    def extra_state_attributes(self):
        v = (self.coordinator.data or {}).get("values", {})
        return {"items": v.get("count"), "warranty_soon": v.get("warranty_soon")}


class _Pushed(TingstedEntity, SensorEntity):
    """Sensor som oppdateres av søk eller webhook, ikke av den jevnlige hentingen."""
    signal = ""

    def __init__(self, entry, key) -> None:
        super().__init__(entry, key)
        self._entry = entry

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_dispatcher_connect(self.hass, self.signal.format(self._entry.entry_id), self.async_write_ha_state))


class SearchResult(_Pushed):
    """Svar på det som står i søkefeltet «Søk»."""
    _attr_icon = "mdi:map-marker-question-outline"
    signal = SIGNAL_SEARCH

    def __init__(self, entry) -> None:
        super().__init__(entry, "search_result")

    @property
    def native_value(self):
        s = self._entry.runtime_data.search
        return (s.get("speech") or "")[:250] or None

    @property
    def extra_state_attributes(self):
        s = self._entry.runtime_data.search
        res = []
        for r in s.get("results", [])[:20]:
            it = r.get("item") or {}
            res.append({"name": it.get("name") or (r.get("box") or {}).get("name") or r.get("where"), "qty": it.get("qty"),
                        "where": r.get("where"), "lent_to": it.get("lent_to"), "item_id": it.get("id"),
                        "url": (r.get("box") or {}).get("url")})
        return {"query": s.get("query", ""), "found": s.get("found", False), "results": res}


class LastEvent(_Pushed):
    """Det siste som skjedde i Tingsted (krever webhook)."""
    _attr_icon = "mdi:history"
    signal = SIGNAL_EVENT

    def __init__(self, entry) -> None:
        super().__init__(entry, "last_event")

    @property
    def native_value(self):
        return (self._entry.runtime_data.last_event.get("text") or "")[:250] or None

    @property
    def extra_state_attributes(self):
        e = dict(self._entry.runtime_data.last_event)
        e.pop("text", None)
        return e


class StatSensor(TingstedEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry, spec: Spec) -> None:
        super().__init__(entry, spec.key)
        self.spec = spec
        self._attr_icon = spec.icon
        self._attr_entity_registry_enabled_default = spec.default_on   # de minst brukte er av til du slår dem på

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("stats", {}).get(self.spec.stat)

    @property
    def extra_state_attributes(self):
        if self.spec.key not in ("lent", "lent_overdue"):
            return None
        items = (self.coordinator.data or {}).get("lent", {}).get("items", [])
        if self.spec.key == "lent_overdue":
            items = [i for i in items if i.get("overdue")]
        return {"items": [{"id": i["id"], "name": i["name"], "lent_to": i.get("lent_to"), "since": i.get("lent_at"),
                           "due": i.get("lent_due"), "overdue": i.get("overdue"), "where": i.get("where")} for i in items[:50]]}
