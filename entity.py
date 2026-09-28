"""Felles for Tingsted-enhetene: én enhet (device) per husstand."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class TingstedEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, entry, key: str) -> None:
        super().__init__(entry.runtime_data.coordinator)
        info = entry.runtime_data.info
        hh = info.get("household", {})
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=f"Tingsted {hh.get('name', '')}".strip(),
            manufacturer="Tingsted",
            sw_version=str(info.get("version", "")),
            configuration_url=entry.runtime_data.client.url,
            entry_type=DeviceEntryType.SERVICE,
        )
