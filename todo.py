"""Utlånt som en huskeliste i HA: kryss av når noe er levert tilbake."""
from __future__ import annotations

from datetime import date, datetime

from homeassistant.components.todo import TodoItem, TodoItemStatus, TodoListEntity, TodoListEntityFeature
from homeassistant.exceptions import HomeAssistantError

from .api import TingstedError
from .entity import TingstedEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([LentList(entry)])


class LentList(TingstedEntity, TodoListEntity):
    def __init__(self, entry) -> None:
        super().__init__(entry, "lent_list")
        self._entry = entry
        if entry.runtime_data.can_write:
            self._attr_supported_features = TodoListEntityFeature.UPDATE_TODO_ITEM | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM

    @property
    def todo_items(self) -> list[TodoItem]:
        out = []
        for i in (self.coordinator.data or {}).get("lent", {}).get("items", []):
            due = date.fromtimestamp(i["lent_due"]) if i.get("lent_due") else None
            out.append(TodoItem(uid=str(i["id"]), summary=f"{i['name']} – {i.get('lent_to') or '?'}",
                                status=TodoItemStatus.NEEDS_ACTION, due=due,
                                description=f"Hører hjemme i {i.get('where', '')}"))
        return out

    async def async_update_todo_item(self, item: TodoItem) -> None:
        client = self._entry.runtime_data.client
        try:
            if item.status == TodoItemStatus.COMPLETED:
                await client.return_item(int(item.uid))
            elif item.due:
                d = item.due if isinstance(item.due, date) and not isinstance(item.due, datetime) else item.due.date()
                await client.update_item(int(item.uid), lent_due=datetime(d.year, d.month, d.day, 23, 59).timestamp())
        except TingstedError as e:
            raise HomeAssistantError(str(e)) from e
        await self.coordinator.async_request_refresh()
