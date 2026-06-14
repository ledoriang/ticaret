from datetime import datetime, time

from pydantic import BaseModel

from trading.core.enums import AssetClass


class MarketHours(BaseModel):
    always_open: bool = False
    open_time: time | None = None
    close_time: time | None = None
    timezone: str = "UTC"

    def is_open(self, dt: datetime | None = None) -> bool:
        if self.always_open:
            return True
        dt = dt or datetime.now()
        if self.open_time and self.close_time:
            t = dt.time()
            if self.close_time > self.open_time:
                return self.open_time <= t <= self.close_time
            return t >= self.open_time or t <= self.close_time
        return True


def get_market_hours(asset_class: AssetClass) -> MarketHours:
    if asset_class == AssetClass.CRYPTO:
        return MarketHours(always_open=True)
    return MarketHours(
        always_open=False,
        open_time=time(9, 30),
        close_time=time(16, 0),
        timezone="US/Eastern",
    )
