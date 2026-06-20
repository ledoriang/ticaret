from dataclasses import dataclass, field

import httpx

from trading.core.config import AlertsConfig


@dataclass
class AlertMessage:
    title: str
    description: str
    severity: str = "info"
    fields: list[dict[str, str]] = field(default_factory=list)
    timestamp: str = ""
    _color_map: dict[str, int] = field(
        default_factory=lambda: {"info": 5814783, "warning": 16766720, "critical": 15548997}
    )


class DiscordAlert:
    def __init__(self, config: AlertsConfig) -> None:
        self.webhook_url = config.discord_webhook_url
        self._client = httpx.AsyncClient()

    def _build_embed(self, msg: AlertMessage) -> dict[str, object]:
        embed: dict[str, object] = {
            "title": msg.title,
            "description": msg.description,
            "color": msg._color_map.get(msg.severity, 5814783),
            "fields": [
                {"name": f["name"], "value": f["value"], "inline": True} for f in msg.fields
            ],
        }
        if msg.timestamp:
            embed["timestamp"] = msg.timestamp
        return embed

    async def send(self, msg: AlertMessage) -> None:
        if not self.webhook_url:
            return
        payload = {"embeds": [self._build_embed(msg)]}
        try:
            resp = await self._client.post(self.webhook_url, json=payload)
            resp.raise_for_status()
        except httpx.HTTPError:
            pass

    async def send_plain(self, text: str) -> None:
        if not self.webhook_url:
            return
        try:
            resp = await self._client.post(self.webhook_url, content=text)
            resp.raise_for_status()
        except httpx.HTTPError:
            pass

    async def close(self) -> None:
        await self._client.aclose()
