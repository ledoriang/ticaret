# PyO3 Hybrid Pathway

## When to Use This

Phase 4 is **conditional**. It is only executed if profiling reveals that Python is a real bottleneck. The most likely candidates are:

- Backtesting simulation iterating millions of bars with position tracking
- Batch indicator computation across hundreds of tickers simultaneously
- Monte Carlo VaR simulation for risk scenario modeling

If Phase 1-3 run smoothly and backtesting completes in acceptable time, skip this phase entirely.

## What Moves to Rust

| Module | Why | PyO3 Boundary |
|---|---|---|
| Backtesting simulation engine | Iterating millions of bars with position tracking, PnL calculation | `rust_kernel.backtest.simulate()` — takes numpy arrays, returns equity curve |
| Batch indicator computation | Computing 20+ indicators across 500 tickers simultaneously | `rust_kernel.indicators.compute()` — replaces pandas-ta in hot paths |
| Risk scenario modeling | Monte Carlo VaR across portfolio positions | `rust_kernel.risk.var_simulation()` — takes position arrays, returns VaR |

## What Stays in Python Forever

- Orchestration and event bus (I/O bound, not CPU bound)
- Strategy logic (should be quick to write and iterate on)
- Broker API calls (network bound)
- Database access (I/O bound)
- Configuration and CLI
- Monitoring, alerting, logging
- Sentiment pipeline (calling Ollama, parsing text)

## Architecture

```
+--------------------------------------------------------+
|                 HIGH-LEVEL PYTHON LAYER                 |
|  - Ingests Twitter/Reddit data                         |
|  - Calls Ollama / LLM for Sentiment Analysis           |
|  - Manages Web UI / Orchestration dashboards           |
|  - Handles all I/O (HTTP, WS, DB, Redis)               |
+---------------------------+----------------------------+
                            |
           PyO3 Bridge      | (Passes numpy arrays)
                            v
+--------------------------------------------------------+
|                  COMPILED RUST KERNEL                  |
|  - Blazing fast, multi-threaded backtesting simulation  |
|  - Deterministic execution without Garbage Collection  |
|  - Batch indicator computation on raw arrays            |
|  - Monte Carlo VaR simulation                          |
+--------------------------------------------------------+
```

## The PyO3 Bridge

Rust functions are compiled into a native Python module via `maturin`. From Python's perspective, calling Rust code is identical to calling any other Python module:

```python
# Python code — no change to the rest of the stack

from trading.core.config import settings

if settings.use_rust_backtester:
    from rust_kernel.backends import simulate
else:
    from trading.backtest.runner import simulate

# The calling code doesn't know or care which implementation it's using.
equity_curve = simulate(bars, signals, initial_capital)
```

## Directory Structure

```
src/trading/rust_kernel/
├── Cargo.toml              # Rust dependencies (pyo3, numpy)
├── pyproject.toml           # maturin build config
└── src/
    └── lib.rs               # Module entry point
```

### Cargo.toml (Initial Stub)

```toml
[package]
name = "rust-kernel"
version = "0.1.0"
edition = "2021"

[lib]
name = "rust_kernel"
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0.22", features = ["extension-module"] }
numpy = "0.22"

# Phase 5 additions:
# tokio = "1"           # For async if needed
# serde = { version = "1", features = ["derive"] }
```

### lib.rs (Initial Stub)

```rust
use pyo3::prelude::*;

#[pymodule]
fn rust_kernel(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Phase 5: Add actual functions here
    // m.add_function(wrap_pyfunction!(simulate, m)?)?;
    // m.add_function(wrap_pyfunction!(compute_indicators, m)?)?;
    // m.add_function(wrap_pyfunction!(var_simulation, m)?)?;
    Ok(())
}
```

## Migration Steps (When Phase 5 Is Triggered)

### 1. Profile

```bash
py-spy record --format speedscope --output profile.speedscope -- python -m trading backtest --strategy sma_crossover --symbol BTC/USDT --start 2020-01-01 --end 2025-01-01
```

Identify functions spending > 50% of execution time in pure computation (not I/O).

### 2. Port One Function

Start with the backtest simulation engine:
use pyo3::prelude::*;
use numpy::PyArray1;

#[pyfunction]
fn simulate(
    py: Python<'_>,
    timestamps: &PyArray1<i64>,
    opens: &PyArray1<f64>,
    highs: &PyArray1<f64>,
    lows: &PyArray1<f64>,
    closes: &PyArray1<f64>,
    signal_flags: &PyArray1<i32>,  // 1=buy, -1=sell, 0=hold
    initial_capital: f64,
) -> PyResult<Py<PyArray1<f64>>> {
    // Rust implementation of backtest simulation
    // Returns equity curve as numpy array
    let equity_curve = /* ... compute ... */;
    Ok(equity_curve.into_pyarray(py).into())
}
```

### 3. Compile and Import

```bash
cd src/trading/rust_kernel
maturin develop --release
```

```python
import rust_kernel
result = rust_kernel.simulate(timestamps, opens, highs, lows, closes, signal_flags, 10000.0)
```

### 4. Validate

- Run the same backtest with both Python and Rust implementations
- Assert equity curves are identical (within floating point tolerance)
- Run existing test suite with `use_rust_backtester: true`

### 5. Toggle via Config

```yaml
# configs/live_micro.yaml
performance:
  use_rust_backtester: true
  use_rust_indicators: false   # Enable when implemented and validated
```

## Performance Targets

| Function | Python Baseline | Rust Target | Speedup |
|---|---|---|---|
| Backtest simulation (1M bars) | ~30s | ~2s | > 10x |
| Batch indicators (500 tickers, 20 indicators) | ~45s | ~3s | > 10x |
| Monte Carlo VaR (10K simulations) | ~20s | ~1.5s | > 10x |

If measured speedup is < 3x, the migration is not worth the complexity cost. Re-evaluate whether the bottleneck is actuallyCPU or if it's I/O that Python async can handle.

## Anti-Patterns to Avoid

- **Don't move I/O to Rust.** Network calls, database queries, and WebSocket handling belong in Python. Rust cannot make HTTP calls faster than Python + httpx.
- **Don't move strategy logic to Rust.** Strategies should be quick to write, iterate on, and debug. The performance gain is negligible compared to the development cost.
- **Don't move configuration to Rust.** YAML parsing, environment variable reading, and Pydantic validation are Python's strength.
- **Don't prematurely optimize.** Only port a function to Rust after profiling proves it's a bottleneck and a vectorized Python alternative (numpy/polars/numba) has been attempted first.

## Build Process

Rust compilation is handled by `maturin` and integrated into the project's build pipeline:

```bash
# Development build (fast, includes debug symbols)
maturin develop

# Release build (slow, optimized)
maturin develop --release

# Or via uv (once configured in pyproject.toml)
uv pip install -e .
```

The CI pipeline runs `maturin develop --release` before running the test suite to ensure the Rust kernel compiles and is importable.