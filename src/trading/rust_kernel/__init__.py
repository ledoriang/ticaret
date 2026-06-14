"""Rust kernel stub — Phase 5 will implement the high-performance backtest engine here.

This package is compiled via maturin. The Rust source is in src/trading/rust_kernel/src/lib.rs.
Until Phase 5, import succeeds but only provides a ping() stub.
"""

try:
    from rust_kernel import ping  # type: ignore[import-untyped,unused-ignore]
except ImportError:

    def ping() -> str:
        return "rust_kernel: not yet compiled (run `maturin develop` in src/trading/rust_kernel)"
