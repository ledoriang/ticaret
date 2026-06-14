from prometheus_client import Counter, Gauge, start_http_server

orders_placed = Counter("trading_orders_placed_total", "Total orders placed", ["broker", "symbol"])
fills_received = Counter(
    "trading_fills_received_total", "Total fills received", ["broker", "symbol"]
)
strategy_signals = Counter(
    "trading_strategy_signals_total", "Strategy signals generated", ["strategy", "side"]
)
risk_blocks = Counter("trading_risk_blocks_total", "Signals blocked by risk", ["rule"])
orders_cancelled = Counter("trading_orders_cancelled_total", "Orders cancelled", ["broker"])

portfolio_value = Gauge("trading_portfolio_value", "Current portfolio value")
open_positions = Gauge("trading_open_positions", "Number of open positions")
current_drawdown = Gauge("trading_current_drawdown_pct", "Current drawdown percentage")
cash_balance = Gauge("trading_cash_balance", "Cash balance")
buying_power = Gauge("trading_buying_power", "Buying power")

connection_status = Gauge(
    "trading_connection_status",
    "Broker connection status (1=connected)",
    ["broker"],
)


def start_metrics_server(port: int = 8000) -> None:
    start_http_server(port)
