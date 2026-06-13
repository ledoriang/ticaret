use pyo3::prelude::*;

/// Stub function — Phase 5 will implement the backtest kernel here.
#[pyfunction]
fn ping() -> &'static str {
    "rust_kernel: pong"
}

/// A Python module implemented in Rust.
#[pymodule]
fn rust_kernel(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(ping, m)?)?;
    Ok(())
}
