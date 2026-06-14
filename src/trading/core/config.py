from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


class DatabaseConfig(BaseModel):
    host: str = "localhost"
    port: int = 5432
    name: str = "trading"
    user: str = "trading"
    password: str = "trading_dev"


class RedisConfig(BaseModel):
    host: str = "localhost"
    port: int = 6379


class BrokerInstanceConfig(BaseModel):
    api_key: str = ""
    api_secret: str = ""
    testnet: bool = True
    paper: bool = False


class ActiveBrokersConfig(BaseModel):
    crypto: str = "binance"
    equity: str = "alpaca"


class BrokersConfig(BaseModel):
    active: ActiveBrokersConfig = Field(default_factory=ActiveBrokersConfig)
    binance: BrokerInstanceConfig = Field(default_factory=BrokerInstanceConfig)
    alpaca: BrokerInstanceConfig = Field(default_factory=BrokerInstanceConfig)
    paper: dict[str, Any] = Field(
        default_factory=lambda: {
            "simulated_slippage": 0.001,
            "simulated_fee_rate": 0.001,
        }
    )


class AlertsConfig(BaseModel):
    discord_webhook_url: str = ""


class MonitoringConfig(BaseModel):
    prometheus_port: int = 8000
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)


class CommissionConfig(BaseModel):
    maker: float = 0.001
    taker: float = 0.001


class SlippageConfig(BaseModel):
    basis_points: int = 5


class BacktestConfig(BaseModel):
    commission: CommissionConfig = Field(default_factory=CommissionConfig)
    slippage: SlippageConfig = Field(default_factory=SlippageConfig)


class TradingConfig(BaseModel):
    execution_mode: Literal["dry_run", "paper", "live"] = "dry_run"
    redis: RedisConfig = Field(default_factory=RedisConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    brokers: BrokersConfig = Field(default_factory=BrokersConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)


def load_config(path: str | Path = "configs/development.yaml") -> TradingConfig:
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    return TradingConfig.model_validate(raw)
