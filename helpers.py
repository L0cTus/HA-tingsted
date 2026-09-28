"""Små hjelpere som deles mellom plattformene."""
from __future__ import annotations


def event_text(d: dict) -> str:
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


SIGNAL_SEARCH = "tingsted_search_{}"
SIGNAL_EVENT = "tingsted_event_{}"
