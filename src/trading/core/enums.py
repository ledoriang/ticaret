from enum import StrEnum, auto


class AssetClass(StrEnum):
    CRYPTO = auto()
    EQUITY = auto()


class Side(StrEnum):
    BUY = auto()
    SELL = auto()


class OrderType(StrEnum):
    MARKET = auto()
    LIMIT = auto()
    STOP = auto()
    STOP_LIMIT = auto()


class OrderStatus(StrEnum):
    PENDING = auto()
    SUBMITTED = auto()
    FILLED = auto()
    PARTIALLY_FILLED = auto()
    CANCELED = auto()
    REJECTED = auto()
    EXPIRED = auto()


class TimeInForce(StrEnum):
    GTC = auto()
    IOC = auto()
    FOK = auto()
    DAY = auto()
