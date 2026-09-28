"""Problem-sensor: noe er lånt ut og over fristen."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity

from .entity import TingstedEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([OverdueSensor(entry)])


class OverdueSensor(TingstedEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, entry) -> None:
        super().__init__(entry, "overdue")

    @property
    def is_on(self) -> bool:
        return bool((self.coordinator.data or {}).get("stats", {}).get("lent_overdue"))

    @property
    def extra_state_attributes(self):
        items = [i for i in (self.coordinator.data or {}).get("lent", {}).get("items", []) if i.get("overdue")]
        return {"items": [f"{i['name']} ({i.get('lent_to')})" for i in items[:20]]}
