"""Sensorer: kasser, ting, steder, utlånt, over fristen og AI-kø."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity, SensorStateClass

from .entity import TingstedEntity


@dataclass(frozen=True)
class Spec:
    key: str
    stat: str
    icon: str


SPECS = [
    Spec("boxes", "boxes", "mdi:package-variant-closed"),
    Spec("items", "items", "mdi:format-list-bulleted"),
    Spec("items_total", "items_total", "mdi:counter"),
    Spec("places", "places", "mdi:home-city-outline"),
    Spec("shelves", "shelves", "mdi:bookshelf"),
    Spec("lent", "lent", "mdi:hand-extended-outline"),
    Spec("lent_overdue", "lent_overdue", "mdi:clock-alert-outline"),
    Spec("ai_queue", "ai_queue", "mdi:robot-outline"),
]


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    stats = entry.runtime_data.coordinator.data.get("stats", {})
    async_add_entities(StatSensor(entry, s) for s in SPECS if not (s.key == "ai_queue" and stats.get("ai_queue") is None))


class StatSensor(TingstedEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry, spec: Spec) -> None:
        super().__init__(entry, spec.key)
        self.spec = spec
        self._attr_icon = spec.icon

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
