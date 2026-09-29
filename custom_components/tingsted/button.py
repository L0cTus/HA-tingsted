"""Knapp: hent alt på nytt fra Tingsted med en gang."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity

from .entity import TingstedEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([RefreshButton(entry)])


class RefreshButton(TingstedEntity, ButtonEntity):
    _attr_icon = "mdi:refresh"

    def __init__(self, entry) -> None:
        super().__init__(entry, "refresh")

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
