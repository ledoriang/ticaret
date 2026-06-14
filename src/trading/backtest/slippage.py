from trading.core.config import SlippageConfig
from trading.core.enums import Side


class SlippageModel:
    def __init__(self, config: SlippageConfig | None = None) -> None:
        self.config = config or SlippageConfig()

    def slippage_per_share(self, price: float) -> float:
        return price * self.config.basis_points / 10_000

    def apply(self, price: float, side: Side) -> float:
        sps = self.slippage_per_share(price)
        if side == Side.BUY:
            return price + sps
        return price - sps

    def compute_cost(self, price: float, quantity: float, _side: Side) -> float:
        return self.slippage_per_share(price) * quantity
