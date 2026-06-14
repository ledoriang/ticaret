from trading.core.config import CommissionConfig


class CommissionModel:
    def __init__(self, config: CommissionConfig | None = None) -> None:
        self.config = config or CommissionConfig()

    def compute(self, price: float, quantity: float, is_taker: bool = True) -> float:
        rate = self.config.taker if is_taker else self.config.maker
        return price * quantity * rate

    def compute_entry_exit(self, entry_price: float, exit_price: float, quantity: float) -> float:
        return self.compute(entry_price, quantity) + self.compute(exit_price, quantity)
