from pathlib import Path

import yaml

from trading.core.config import TradingConfig, load_config


class TestTradingConfig:
    def test_default_config(self) -> None:
        config = TradingConfig()
        assert config.execution_mode == "dry_run"
        assert config.redis.host == "localhost"
        assert config.database.port == 5432

    def test_load_config_from_yaml(self, tmp_path: Path) -> None:
        cfg_data = {
            "execution_mode": "paper",
            "redis": {"host": "redis.example.com", "port": 6379},
            "database": {"host": "db.example.com", "port": 5432, "name": "prod"},
            "brokers": {
                "active": {"crypto": "binance"},
                "binance": {"api_key": "key123", "testnet": True},
            },
            "monitoring": {"prometheus_port": 8000, "alerts": {"discord_webhook_url": ""}},
        }
        cfg_path = tmp_path / "test_config.yaml"
        with open(cfg_path, "w") as f:
            yaml.dump(cfg_data, f)

        config = load_config(cfg_path)
        assert config.execution_mode == "paper"
        assert config.redis.host == "redis.example.com"
        assert config.brokers.binance.api_key == "key123"
