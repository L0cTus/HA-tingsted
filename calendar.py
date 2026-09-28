"""Kalender: når utlånte ting skal leveres tilbake, og når garantier går ut."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent

from .entity import TingstedEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([TingstedCalendar(entry)])


class TingstedCalendar(TingstedEntity, CalendarEntity):
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, entry) -> None:
        super().__init__(entry, "calendar")

    def _events(self) -> list[CalendarEvent]:
        data = self.coordinator.data or {}
        out = []
        for i in data.get("lent", {}).get("items", []):
            if i.get("lent_due"):
                d = date.fromtimestamp(i["lent_due"])
                out.append(CalendarEvent(start=d, end=d + timedelta(days=1), uid=f"lent-{i['id']}",
                                         summary=f"Lever tilbake: {i['name']} ({i.get('lent_to') or '?'})",
                                         description=f"Hører hjemme i {i.get('where', '')}"))
        for i in data.get("values", {}).get("items", []):
            if i.get("warranty"):
                d = date.fromtimestamp(i["warranty"])
                out.append(CalendarEvent(start=d, end=d + timedelta(days=1), uid=f"warranty-{i['id']}",
                                         summary=f"Garanti slutter: {i['name']}", description=f"Ligger i {i.get('where', '')}"))
        return sorted(out, key=lambda e: e.start)

    @property
    def event(self) -> CalendarEvent | None:
        today = date.today()
        return next((e for e in self._events() if e.end > today), None)

    async def async_get_events(self, hass, start_date: datetime, end_date: datetime) -> list[CalendarEvent]:
        s, e = start_date.date(), end_date.date()
        return [ev for ev in self._events() if ev.end > s and ev.start <= e]
