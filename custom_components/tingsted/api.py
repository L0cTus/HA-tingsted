"""Klient for Tingsted sitt API (/api/v1). Ingen Home Assistant-avhengigheter, så den kan testes alene.

`session` er en aiohttp.ClientSession (i HA: async_get_clientsession(hass)).
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
from typing import Any


class TingstedError(Exception):
    """Noe gikk galt mot Tingsted."""


class TingstedAuthError(TingstedError):
    """Feil eller slettet API-nøkkel."""


class TingstedConnectionError(TingstedError):
    """Fikk ikke kontakt."""


def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    """Sjekker X-Tingsted-Signature: sha256=<hmac>."""
    if not secret or not header or not header.startswith("sha256="):
        return False
    want = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, header[7:])


class TingstedClient:
    def __init__(self, session, url: str, key: str, timeout: float = 15) -> None:
        self.session = session
        self.url = url.rstrip("/")
        self.key = key.strip()
        self.timeout = timeout

    async def _call(self, method: str, path: str, *, params: dict | None = None, json: Any = None) -> Any:
        headers = {"Authorization": f"Bearer {self.key}", "Accept": "application/json"}
        try:
            async with asyncio.timeout(self.timeout):
                async with self.session.request(method, f"{self.url}/api/v1{path}", headers=headers,
                                                params=params, json=json) as resp:
                    if resp.status == 401:
                        raise TingstedAuthError((await self._json(resp)).get("error", "Ugyldig API-nøkkel"))
                    data = await self._json(resp)
                    if resp.status >= 400:
                        raise TingstedError(data.get("error") or f"HTTP {resp.status}")
                    return data
        except TingstedError:
            raise
        except (asyncio.TimeoutError, OSError) as e:
            raise TingstedConnectionError(f"Får ikke kontakt med Tingsted: {e.__class__.__name__}") from e
        except Exception as e:  # aiohttp.ClientError og lignende
            raise TingstedConnectionError(f"Får ikke kontakt med Tingsted: {e}") from e

    @staticmethod
    async def _json(resp) -> dict:
        try:
            data = await resp.json(content_type=None)
        except TypeError:          # klienter uten content_type-argument
            data = await resp.json()
        except Exception:
            return {}
        return data if isinstance(data, dict) else {"data": data}

    # ---- lese
    async def info(self) -> dict:
        return await self._call("GET", "")

    async def stats(self) -> dict:
        return await self._call("GET", "/stats")

    async def lent(self) -> dict:
        return await self._call("GET", "/lent")

    async def where(self, q: str) -> dict:
        return await self._call("GET", "/hvor", params={"q": q})

    async def search(self, q: str) -> dict:
        return await self._call("GET", "/search", params={"q": q})

    async def history(self, limit: int = 20) -> dict:
        return await self._call("GET", "/history", params={"limit": limit})

    async def values(self) -> dict:
        return await self._call("GET", "/values")

    async def box(self, ref: str) -> dict:
        return await self._call("GET", f"/boxes/{ref}")

    # ---- skrive (krever nøkkel med skrivetilgang)
    async def add_items(self, box: str, items: list[str]) -> dict:
        return await self._call("POST", f"/boxes/{box}/items", json={"items": items})

    async def update_item(self, item_id: int, **fields) -> dict:
        return await self._call("PATCH", f"/items/{int(item_id)}", json=fields)

    async def return_item(self, item_id: int) -> dict:
        return await self._call("POST", f"/items/{int(item_id)}/return")

    async def create_webhook(self, url: str, label: str = "Home Assistant") -> dict:
        return await self._call("POST", "/webhooks", json={"url": url, "label": label, "events": ["*"]})

    async def delete_webhook(self, hook_id: int) -> dict:
        return await self._call("DELETE", f"/webhooks/{int(hook_id)}")
